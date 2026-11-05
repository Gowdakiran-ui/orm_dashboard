"""Seeded top-5 executives / competitors (services/seeding, the engines' seeded gates, backfill caps, per-run cap).

In-memory SQLite only. DATABASE_URL is an unreachable dummy, the LLM and Google News are injected fakes, so nothing
here can reach a real database, queue, LLM or the network.
"""
import os
import sys
import uuid
import datetime as dt
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityKeyword, EntityMention
from app.models.document import Document
from app.models.rss_feed import RSSFeed
from app.models.seeded_entity import SeededEntity
from app.models.backfill import BackfillSlice
from app.services.seeding import aliases as alias_mod
from app.services.seeding import gates, proposer, service, validator
from app.services.seeding.proposer import SeedingAborted


@compiles(PG_UUID, "sqlite")
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _client(db, name="Godrej Properties", domain="godrejproperties.com"):
    c = Client(id=uuid.uuid4(), name=name)
    db.add(c)
    brand = Entity(id=uuid.uuid4(), client_id=c.id, name=name, entity_type="brand", domain=domain)
    db.add(brand)
    db.commit()
    return c, brand


# ------------------------------------------------------------------------------------------------ proposer
class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._p = payload
        self.text = "boom"

    def json(self):
        return self._p


def _ok_payload(content=None, annotations=True):
    content = content or ('```json\n{"executives":[{"name":"A B","role":"CEO","source_urls":["https://x.com/a"]}],'
                          '"competitors":[{"name":"DLF","context_term":"real estate","source_urls":[]}]}\n```')
    msg = {"content": content}
    if annotations:
        msg["annotations"] = [{"type": "url_citation", "url_citation": {"url": "https://example.com/cite"}}]
    return {"choices": [{"message": msg}], "usage": {"cost": 0.0141}}


def test_proposer_aborts_without_a_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SeedingAborted):
        proposer.propose("Godrej Properties", post=lambda *a, **k: _Resp(200, _ok_payload()))


def test_proposer_uses_the_web_plugin_on_haiku_45_and_returns_cost_and_citations():
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        return _Resp(200, _ok_payload())

    out = proposer.propose("Godrej Properties", "godrejproperties.com", "real estate", post=post, api_key="k")
    assert seen["body"]["model"] == "anthropic/claude-haiku-4.5"
    assert seen["body"]["plugins"] == [{"id": "web", "max_results": 5}]
    assert out["cost_usd"] == pytest.approx(0.0141) and out["citations"] == ["https://example.com/cite"]
    assert out["executives"][0]["name"] == "A B" and out["competitors"][0]["name"] == "DLF"


@pytest.mark.parametrize("resp", [_Resp(500), _Resp(200, _ok_payload(annotations=False)), _Resp(200, _ok_payload(content="not json"))])
def test_proposer_aborts_on_a_failed_or_ungrounded_web_call_and_never_retries_on_the_plain_model(resp):
    calls = []

    def post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return resp

    with pytest.raises(SeedingAborted):
        proposer.propose("X", post=post, api_key="k")
    assert len(calls) == 1 and "plugins" in calls[0]          # exactly one call, and it was the web one


def test_proposer_returns_slotted_candidates_and_caps_the_lists():
    many = ",".join('{"name":"M%d","source_urls":["https://x.com"]}' % i for i in range(12))
    comps = ",".join('{"name":"C%d","source_urls":["https://x.com"]}' % i for i in range(12))
    content = ('{"company":{"website":"https://x.com","primary_market":"India"},"executives":{"chairperson":{"name":"Chair One"},"md_ceo":null,'
               '"cfo":{"name":"Cee Fo"},"founders":[{"name":"Chair One"}],"other_management":[%s],"directors":[{"name":"Dir A"}]},"competitors":[%s]}' % (many, comps))
    out = proposer.propose("X", post=lambda *a, **k: _Resp(200, _ok_payload(content=content)), api_key="k")
    slots = [(e["name"], e["slot"]) for e in out["executives"]]
    assert slots[:2] == [("Chair One", "chairperson"), ("Cee Fo", "cfo")]                       # null slot skipped, role order kept
    assert slots.count(("Chair One", "chairperson")) == 1 and ("Chair One", "founder") not in slots      # the same person is counted once, in the senior slot
    assert len([1 for _, sl in slots if sl == "management"]) == 8 and slots[-1] == ("Dir A", "director")  # 8 other-management candidates, directors last
    assert len(out["competitors"]) == 8
    assert out["company"]["primary_market"] == "India"


# ---------------------------------------------------------------------------------------------- validator
def test_slices_are_four_six_month_windows_over_24_months():
    s = validator.slices(dt.date(2026, 11, 4))
    assert len(s) == 4
    assert all(a < b for a, b in s) and all(s[i][1] == s[i + 1][0] for i in range(3))
    assert (s[-1][1] - s[0][0]).days in range(725, 735)


def _fetch_returning(n_per_slice, record=None):
    def fetch(query, a, b):
        if record is not None:
            record.append((query, a, b))
        return [object()] * n_per_slice
    return fetch


def _text_with(*names):
    return lambda url: " ".join(names)


def _pages(mapping):
    return lambda url: mapping.get(url)


def _two(n=(1, 1, 0, 0)):
    it = iter(n)
    return lambda q, a, b: [object()] * next(it, 0)


def test_executive_rule_news_count_or_the_name_with_its_role_on_a_company_nse_bse_page_or_on_two_independent_domains():
    base = {"name": "Gaurav Pandey", "slot": "md_ceo", "role": "Managing Director & CEO"}
    news = "https://news.example.com/a"
    three = validator.validate_executive({**base, "source_urls": [news]}, "Godrej Properties", [], _fetch_returning(1), fetch_text=_pages({}))     # 4 items
    assert three["accepted"] and three["method"] == "news count"
    role_page = "Our team: Gaurav Pandey, Managing Director and CEO of the company"
    name_only = "Photo gallery: Gaurav Pandey at the opening ceremony"
    # one news page with name + role is NOT enough for 1-2 items
    one = validator.validate_executive({**base, "source_urls": [news]}, "Godrej Properties", [], _two(), fetch_text=_pages({news: role_page}))
    assert not one["accepted"] and one["needs_better_sources"]
    # the company domain with name + role is
    own = "https://www.godrejproperties.com/leadership"
    ok = validator.validate_executive({**base, "source_urls": [own]}, "Godrej Properties", [], _two(), fetch_text=_pages({own: role_page}))
    assert ok["accepted"] and ok["method"] == "company page" and ok["verified_page"] == own
    # so is NSE/BSE
    nse = "https://www.bseindia.com/x.html"
    assert validator.validate_executive({**base, "source_urls": [nse]}, "Godrej Properties", [], _two(), fetch_text=_pages({nse: role_page}))["method"] == "exchange filing"
    # the name without the role title does not count
    no_role = validator.validate_executive({**base, "source_urls": [own]}, "Godrej Properties", [], _two(), fetch_text=_pages({own: name_only}))
    assert not no_role["accepted"]
    # two independent domains with name + role
    a, b = "https://news.example.com/a", "https://other.example.org/b"
    two_dom = validator.validate_executive({**base, "source_urls": [a, b]}, "Godrej Properties", [], _two(), fetch_text=_pages({a: role_page, b: role_page}))
    assert two_dom["accepted"] and two_dom["method"] == "two independent domains"
    same_dom = validator.validate_executive({**base, "source_urls": [a, a + "2"]}, "Godrej Properties", [], _two(), fetch_text=_pages({a: role_page, a + "2": role_page}))
    assert not same_dom["accepted"]                                              # two pages on one domain are not independent
    zero = validator.validate_executive({**base, "source_urls": [own]}, "Godrej Properties", ["godrejproperties.com"], _fetch_returning(0), fetch_text=_pages({own: role_page}))
    assert not zero["accepted"] and "no Google News item" in zero["reason"]
    no_source = validator.validate_executive(base, "Godrej Properties", [], _fetch_returning(50), fetch_text=_pages({}))
    assert not no_source["accepted"] and no_source["reason"] == "no source URL"


def test_role_matching_finds_the_title_next_to_the_name_only():
    t = validator.role_terms("cfo", "CFO")
    assert validator.page_has_name_and_role("Mr. Rajendra Khetawat, Chief Financial Officer of the Company", "Rajendra Khetawat", t)
    assert validator.page_has_name_and_role("Rajendra Khetawat (CFO) said", "Rajendra Khetawat", t)
    far = "Rajendra Khetawat attended. " + "filler words " * 80 + "The Chief Financial Officer reported."
    assert not validator.page_has_name_and_role(far, "Rajendra Khetawat", t)           # the title is far from the name
    assert not validator.page_has_name_and_role("Chief Financial Officer: someone else", "Rajendra Khetawat", t)


def test_a_pdf_or_failed_fetch_does_not_verify_a_name_and_a_html_page_is_read():
    assert validator.page_names_person("https://x.com/report.pdf", "A B", None) is False
    assert validator.fetch_page_text("https://x.com/a", get=lambda *a, **k: SimpleNamespace(status_code=404, text="x", headers={})) is None
    page = SimpleNamespace(status_code=200, headers={"content-type": "text/html"}, text="<html><body><h1>Our team</h1><p>Gaurav  Pandey - MD&amp;CEO</p></body></html>")
    assert validator.page_names_person("https://x.com/a", "Gaurav Pandey", lambda u: validator.fetch_page_text(u, get=lambda *a, **k: page))


def test_executive_query_is_the_exact_name_and_company_pair():
    rec = []
    validator.validate_executive({"name": "Gaurav Pandey", "source_urls": ["https://x.com"]}, "Godrej Properties", [], _fetch_returning(1, rec))
    assert {q for q, _, _ in rec} == {'"Gaurav Pandey" "Godrej Properties"'}
    assert len(rec) == 4


def test_competitor_needs_twenty_sector_consistent_news_items():
    item = {"name": "DLF", "context_term": "real estate"}
    assert validator.validate_competitor(item, _fetch_returning(5))["accepted"]            # 20 over four slices
    assert not validator.validate_competitor(item, _fetch_returning(4))["accepted"]        # 16
    assert not validator.validate_competitor({"name": "DLF"}, _fetch_returning(50))["accepted"]   # no context term
    rec = []
    validator.validate_competitor(item, _fetch_returning(5, rec))
    assert {q for q, _, _ in rec} == {'"DLF" real estate'}


def test_competitor_query_strips_the_legal_suffix_and_leaves_the_sector_words_unquoted():
    assert validator.competitor_query("DLF Limited", "residential real estate") == '"DLF" residential real estate'
    assert validator.competitor_query("Reliance Industries Limited", "Infrastructure conglomerate") == '"Reliance Industries" Infrastructure conglomerate'


def test_official_source_matches_a_configured_domain_exchange_filings_or_a_host_named_like_the_company():
    f = validator.is_official_source
    assert f("https://www.godrejproperties.com/know-us/leadership", [], "Godrej Properties")
    assert f("https://www.adani.com/about-us/leadership", [], "Adani Group")
    assert f("https://www.easemytrip.com/about-us.html", [], "EaseMyTrip")
    assert not f("https://www.godrejindustries.com/x", [], "Godrej Properties")        # a sister company's site is not this company's
    assert not f("https://blog.example.com/godrejproperties", [], "Godrej Properties")
    assert f("https://ir.example.in/x", ["example.in"], None)                             # a configured domain is authoritative
    assert f("https://nsearchives.nseindia.com/a.pdf", [], None)


def test_a_sister_company_is_not_a_competitor_even_with_a_big_sector_count():
    item = {"name": "Godrej Consumer Products Limited", "context_term": "consumer products"}
    out = validator.validate_competitor(item, _fetch_returning(30), company="Godrej Properties")
    assert not out["accepted"] and "same group" in out["reason"]
    assert validator.validate_competitor({"name": "DLF", "context_term": "real estate"}, _fetch_returning(30), company="Godrej Properties")["accepted"]
    assert validator.is_same_group("Adani Wilmar", "Adani Group")
    assert not validator.is_same_group("Reliance Industries", "Adani Group")


# -------------------------------------------------------------------------------------------------- aliases
def test_multi_word_aliases_are_accepted_single_generic_words_and_person_single_words_rejected():
    parts = alias_mod.split_aliases("Prestige Estates", ["Prestige Estates Projects", "Prestige", "Group", "Presstige"], "competitor")
    assert [a["alias"] for a in parts["accepted"]] == ["Prestige Estates Projects"]
    assert alias_mod.is_bare("L&T") and not alias_mod.is_bare("Tata Sons")
    assert {a["alias"] for a in parts["rejected"]} == {"Prestige", "Group"}               # generic words
    assert [a["alias"] for a in parts["to_measure"]] == ["Presstige"]
    person = alias_mod.split_aliases("Rikant Pittie", ["Rikant Pitti", "Rikant"], "executive")
    assert [a["alias"] for a in person["accepted"]] == ["Rikant Pitti"] and [a["alias"] for a in person["rejected"]] == ["Rikant"]


def _news(*texts):
    return [{"title": t, "summary": ""} for t in texts]


def test_bare_alias_is_enabled_only_when_few_sample_documents_are_false_matches():
    good = _news(*(["Lodha shares rise on NSE, real estate demand"] * 25))
    m = alias_mod.measure_bare_alias("Lodha", "Lodha Group", ["real estate"], lambda q, a, b: good)
    assert m["enabled"] and m["false_rate"] == 0
    noisy = _news(*(["Lodha shares rise on NSE"] * 20 + ["Abhinav Lodha went to a cricket match"] * 10 + ["Lodha clan festival"] * 5))
    m2 = alias_mod.measure_bare_alias("Lodha", "Lodha Group", ["real estate"], lambda q, a, b: noisy)
    assert not m2["enabled"] and m2["false_rate"] > 0.10
    few = _news(*(["Lodha shares"] * 5))
    assert not alias_mod.measure_bare_alias("Lodha", "Lodha Group", [], lambda q, a, b: few)["enabled"]


def test_bare_alias_sample_is_capped_at_fifty_documents():
    seen = []

    def fetch(q, a, b):
        return _news(*(["Lodha real estate"] * 80))

    m = alias_mod.measure_bare_alias("Lodha", "Lodha Group", ["real estate"], fetch)
    assert m["sample"] == 50 and m["with_alias"] == 50


# ----------------------------------------------------------------------------------------------- gate maths
def test_executive_gate_needs_full_name_and_company_in_title_or_lead():
    rows = [
        (1, "Gaurav Pandey: Godrej Properties posts record sales", ""),
        (2, "Gaurav Pandey speaks at a conference", "He leads the company."),
        (3, "Godrej Properties launches Bandra Bay", "Gaurav Pandey, MD & CEO, said"),
        (4, "Pandey says markets are up", "Godrej Properties"),
    ]
    assert gates.person_doc_ids(rows, ["Gaurav Pandey"], ["godrej properties"]) == {1, 3}


def test_competitor_gate_is_about_the_competitor_itself_and_does_not_need_the_client():
    rows = [
        (1, "DLF Q2 profit jumps 20%", ""),                                # one-word name, no context term
        (2, "DLF Limited real estate arm launches Gurugram project", ""),
        (3, "Prestige Estates Projects posts record bookings", ""),         # multi-word name, no context needed
        (4, "Something unrelated", "mentions Godrej Properties only"),
    ]
    out = gates.competitor_doc_ids(rows, ["DLF"], ["real", "estate"])
    assert out == {2}
    # a context word anywhere in the stored text (4th value) is enough for a one-word name that is in the title
    with_ctx = [(1, "DLF Q2 profit jumps 20%", "", 1), (5, "DLF names a new CFO", "", 0)]
    assert gates.competitor_doc_ids(with_ctx, ["DLF"], ["real", "estate"]) == {1}
    assert gates.competitor_doc_ids(rows, ["Prestige Estates"], ["real estate"]) == {3}


# --------------------------------------------------------------------------------------- service (sqlite)
def _plan_fake():
    return {
        "executives": [
            {"name": "Pirojsha Godrej", "role": "Chairperson", "source_urls": ["https://www.godrejproperties.com/p"], "aliases": ["Pirojsha Adi Godrej"]},
            {"name": "Invented Person", "role": "CFO", "source_urls": ["https://blog.example.com/x"]},
        ],
        "competitors": [
            {"name": "DLF", "context_term": "real estate", "source_urls": ["https://example.com"], "aliases": ["DLF Limited"]},
            {"name": "Tiny Co", "context_term": "real estate", "source_urls": []},
        ],
        "cost_usd": 0.0139, "citations": ["https://c.example.com"], "model": proposer.MODEL,
    }


def _no_page(url):
    return None


def _fetch_by_query(query, a, b):
    if "Invented Person" in query or '"Tiny"' in query:
        return []
    return [object()] * 8


def test_apply_creates_active_rows_entities_keywords_and_quoted_feeds_and_holds_back_the_rest(db, monkeypatch):
    monkeypatch.setattr(service, "_refresh_matcher_and_rematch", lambda *a, **k: None)
    c, brand = _client(db)
    out = service.seed_client(db, c.id, apply=True, propose_fn=lambda *a, **k: _plan_fake(), fetch=_fetch_by_query, measure_aliases=False, fetch_text=_no_page)
    assert out["applied"]["active"] == 2 and out["applied"]["needs_review"] == 2 and out["applied"]["created"] == 2
    rows = {r.name: r for r in db.query(SeededEntity).all()}
    assert rows["Pirojsha Godrej"].status == "active" and rows["Pirojsha Godrej"].rank == 1 and rows["Pirojsha Godrej"].validated
    assert rows["Invented Person"].status == "needs_review" and rows["Invented Person"].entity_id is None
    assert rows["Tiny Co"].status == "needs_review"
    # needs_review rows never reach the pages or the engines
    assert [r.name for r in gates.seeded_rows(db, c.id)] == ["Pirojsha Godrej", "DLF"]
    pir = db.query(Entity).filter(Entity.name == "Pirojsha Godrej").one()
    assert pir.entity_type == "person" and db.query(Entity).filter(Entity.name == "DLF").one().entity_type == "competitor"
    kws = {(k.keyword_text, k.category) for k in db.query(EntityKeyword).filter(EntityKeyword.entity_id == pir.id)}
    assert ("Pirojsha Godrej", "PRIMARY") in kws and ("Pirojsha Adi Godrej", "ALIAS") in kws
    urls = {f.feed_url for f in db.query(RSSFeed).all()}
    assert len(urls) == 6                                                   # Google News, GDELT, HN for each of the two active entities
    assert any(u.startswith("https://news.google.com/rss/search?q=%22Pirojsha+Godrej%22+%22Godrej+Properties%22") for u in urls)
    assert any("%22DLF%22+real+estate" in u for u in urls)                   # competitor: quoted name + sector words, NOT the client
    assert not any("DLF" in u and "Godrej" in u for u in urls)
    assert gates.seeded_feed_urls(db, c.id) == urls


def test_the_chosen_list_is_persisted_a_second_apply_needs_an_explicit_refresh_and_links_instead_of_duplicating(db, monkeypatch):
    monkeypatch.setattr(service, "_refresh_matcher_and_rematch", lambda *a, **k: None)
    c, brand = _client(db)
    existing = Entity(id=uuid.uuid4(), client_id=c.id, name="DLF", entity_type="competitor")
    db.add(existing)
    db.commit()
    service.seed_client(db, c.id, apply=True, propose_fn=lambda *a, **k: _plan_fake(), fetch=_fetch_by_query, measure_aliases=False, fetch_text=_no_page)
    with pytest.raises(service.AlreadySeeded):
        service.seed_client(db, c.id, apply=True, propose_fn=lambda *a, **k: _plan_fake(), fetch=_fetch_by_query, measure_aliases=False, fetch_text=_no_page)
    service.seed_client(db, c.id, apply=True, propose_fn=lambda *a, **k: _plan_fake(), fetch=_fetch_by_query, measure_aliases=False, fetch_text=_no_page, refresh=True)
    assert db.query(Entity).filter(Entity.name == "DLF").count() == 1
    assert db.query(SeededEntity).filter(SeededEntity.name == "DLF").one().entity_id == existing.id
    assert db.query(RSSFeed).count() == 6                                   # no duplicate feeds on the refresh


def test_a_near_miss_competitor_name_is_linked_to_the_existing_entity_not_added(db, monkeypatch):
    monkeypatch.setattr(service, "_refresh_matcher_and_rematch", lambda *a, **k: None)
    c, brand = _client(db, "Adani Group", "adani.com")
    existing = Entity(id=uuid.uuid4(), client_id=c.id, name="Reliance Industries", entity_type="competitor")
    db.add(existing)
    db.commit()
    from app.services.intelligence.entity_discovery import entity_discovery_engine as eng
    assert eng._find_near_duplicate_competitor_entity(db, c.id, "Relianca").id == existing.id     # the typo guard
    assert eng._find_near_duplicate_competitor_entity(db, c.id, "Reliance Retail") is None       # same first word: a different company
    assert eng._find_near_duplicate_competitor_entity(db, c.id, "Tata Group") is None


def test_a_seeded_competitor_is_linked_to_an_existing_one_under_a_slightly_different_name(db, monkeypatch):
    monkeypatch.setattr(service, "_refresh_matcher_and_rematch", lambda *a, **k: None)
    c, brand = _client(db)
    existing = {n: Entity(id=uuid.uuid4(), client_id=c.id, name=n, entity_type="competitor") for n in ("DLF", "Prestige Estates", "Lodha")}
    db.add_all(existing.values())
    db.commit()
    assert service.core_name("DLF Limited") == "dlf" and service.core_name("Prestige Estates Projects") == "prestige estates"
    for seeded_name, tracked in (("DLF Limited", "DLF"), ("Prestige Estates Projects", "Prestige Estates"), ("Lodha Group", "Lodha")):
        ent, how = service._dedupe_entity(db, c.id, seeded_name, "competitor")
        assert ent is not None and ent.name == tracked, (seeded_name, ent)
    assert service._dedupe_entity(db, c.id, "Oberoi Realty", "competitor")[0] is None
    assert service._dedupe_entity(db, c.id, "Reliance Retail", "competitor")[0] is None


def test_retire_deactivates_the_feeds_and_leaves_the_entity(db, monkeypatch):
    monkeypatch.setattr(service, "_refresh_matcher_and_rematch", lambda *a, **k: None)
    c, brand = _client(db)
    service.seed_client(db, c.id, apply=True, propose_fn=lambda *a, **k: _plan_fake(), fetch=_fetch_by_query, measure_aliases=False, fetch_text=_no_page)
    out = service.retire(db, c.id, "DLF")
    assert out["retired"] == 1 and out["feeds_deactivated"] == 3
    assert db.query(Entity).filter(Entity.name == "DLF").count() == 1
    assert [r.name for r in gates.seeded_rows(db, c.id)] == ["Pirojsha Godrej"]
    # a refresh does not bring a retired row back
    service.seed_client(db, c.id, apply=True, propose_fn=lambda *a, **k: _plan_fake(), fetch=_fetch_by_query, measure_aliases=False, fetch_text=_no_page, refresh=True)
    assert db.query(SeededEntity).filter(SeededEntity.name == "DLF").one().status == "retired"


def test_dry_run_writes_nothing(db):
    c, brand = _client(db)
    out = service.seed_client(db, c.id, apply=False, propose_fn=lambda *a, **k: _plan_fake(), fetch=_fetch_by_query, measure_aliases=False, fetch_text=_no_page)
    assert out["applied"] is None and db.query(SeededEntity).count() == 0 and db.query(RSSFeed).count() == 0
    text = service.format_plan(out["plan"])
    assert "Pirojsha Godrej" in text and "needs_review" in text and "source: https://www.godrejproperties.com/p" in text


def test_an_aborted_web_call_writes_nothing(db):
    c, brand = _client(db)

    def fail(*a, **k):
        raise SeedingAborted("down")

    with pytest.raises(SeedingAborted):
        service.seed_client(db, c.id, apply=True, propose_fn=fail)
    assert db.query(SeededEntity).count() == 0 and db.query(Entity).count() == 1


def test_gates_are_inert_when_the_table_is_missing():
    engine = create_engine("sqlite:///:memory:")
    s = sessionmaker(bind=engine)()
    assert gates.seeded_rows(s, uuid.uuid4()) == [] and gates.seeded_entity_ids(s, uuid.uuid4()) == set()


# ------------------------------------------------------------------------------------ engines' seeded gates
def _doc(db, title, lead="", published=None):
    d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", title=title, normalized_content=lead or title,
                 published_at=published or dt.datetime.now(dt.timezone.utc))
    db.add(d)
    return d


def test_seeded_competitor_inputs_use_its_own_documents_not_the_brand_gate(db):
    from app.services.intelligence.benchmark_engine import BenchmarkEngine
    c, brand = _client(db)
    seeded = Entity(id=uuid.uuid4(), client_id=c.id, name="Prestige Estates", entity_type="competitor")
    plain = Entity(id=uuid.uuid4(), client_id=c.id, name="Lodha", entity_type="competitor")
    db.add_all([seeded, plain])
    db.commit()
    # 6 documents about Prestige that never mention Godrej; 6 about Lodha that never mention Godrej; 2 about Godrej only
    for ent, name in ((seeded, "Prestige Estates"), (plain, "Lodha")):
        for i in range(6):
            d = _doc(db, f"{name} bookings {i}")
            db.flush()
            db.add(EntityMention(document_id=d.id, entity_id=ent.id, mention_count=1))
    for i in range(2):
        d = _doc(db, f"Godrej Properties news {i}")
        db.flush()
        db.add(EntityMention(document_id=d.id, entity_id=brand.id, mention_count=1))
    db.add(SeededEntity(client_id=c.id, entity_id=seeded.id, kind="competitor", name="Prestige Estates", rank=1, validated=True, status="active"))
    db.commit()

    eng = BenchmarkEngine()
    lookback = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)
    brand_docs = {m.document_id for m in db.query(EntityMention).filter(EntityMention.entity_id == brand.id)}
    overrides = gates.seeded_gate_doc_ids(db, c.id, [seeded.id])
    log = SimpleNamespace(warning=lambda *a, **k: None)
    plain_run = eng._preload_score_inputs(db, c.id, [brand.id, seeded.id, plain.id], lookback, log, brand_doc_ids=brand_docs)
    assert plain_run["mentions_map"].get(seeded.id, 0) == 0 and plain_run["mentions_map"].get(plain.id, 0) == 0   # brand gate: unchanged
    run = eng._preload_score_inputs(db, c.id, [brand.id, seeded.id, plain.id], lookback, log, brand_doc_ids=brand_docs,
                                    entity_doc_overrides=overrides)
    assert run["mentions_map"][seeded.id] == 6                    # its own documents count
    assert run["mentions_map"].get(plain.id, 0) == 0              # a non-seeded competitor still needs the client in the document
    assert run["mentions_map"][brand.id] == 2


def test_executive_engine_scores_a_seeded_person_on_name_plus_company_and_leaves_others_on_the_brand_gate(db, monkeypatch):
    from app.services.intelligence import executive_reputation_engine as mod
    c, brand = _client(db)
    seeded = Entity(id=uuid.uuid4(), client_id=c.id, name="Gaurav Pandey", entity_type="person")
    other = Entity(id=uuid.uuid4(), client_id=c.id, name="Some Analyst", entity_type="person")
    db.add_all([seeded, other])
    db.commit()
    now = dt.datetime.now(dt.timezone.utc)
    old = now - dt.timedelta(days=200)                               # outside 30 days, inside 365
    good = _doc(db, "Gaurav Pandey of Godrej Properties on the launch", published=old)
    wrong = _doc(db, "Gaurav Pandey wins a golf trophy", published=old)         # full name but no company
    brand_only = _doc(db, "Godrej Properties and Some Analyst", published=old)
    db.flush()
    db.add_all([
        EntityMention(document_id=good.id, entity_id=seeded.id, mention_count=1),
        EntityMention(document_id=wrong.id, entity_id=seeded.id, mention_count=1),
        EntityMention(document_id=brand_only.id, entity_id=other.id, mention_count=1),
        EntityMention(document_id=brand_only.id, entity_id=brand.id, mention_count=1),
        EntityMention(document_id=good.id, entity_id=brand.id, mention_count=1),
    ])
    db.add(SeededEntity(client_id=c.id, entity_id=seeded.id, kind="executive", name="Gaurav Pandey", rank=1, validated=True, status="active"))
    db.commit()
    seen = {}

    def fake_eval(self, db_, client_id, exec_entity, doc_ids, *a, **k):
        seen[exec_entity.name] = set(doc_ids)

    monkeypatch.setattr(mod.ExecutiveReputationEngine, "_evaluate_single_executive_optimized", fake_eval)
    mod.ExecutiveReputationEngine().calculate_executive_reputation(db, c.id)
    assert seen["Gaurav Pandey"] == {good.id}                       # full name + company in the title; 200 days old is inside the 365-day window
    assert seen["Some Analyst"] == {brand_only.id}                  # brand gate, unchanged


def test_window_settings_default_to_365_executive_and_90_benchmark_days():
    from app.core.config import settings
    assert settings.EXEC_WINDOW_DAYS == 365 and settings.BENCHMARK_WINDOW_DAYS == 90


# ----------------------------------------------------------------------------------- backfill caps and specs
def test_backfill_plans_seeded_entities_without_youtube_and_with_a_risk_variant(db):
    from app.services.backfill.queries import build_queries
    c, brand = _client(db)
    pir = Entity(id=uuid.uuid4(), client_id=c.id, name="Pirojsha Godrej", entity_type="person")
    dlf = Entity(id=uuid.uuid4(), client_id=c.id, name="DLF", entity_type="competitor")
    old = Entity(id=uuid.uuid4(), client_id=c.id, name="Plain Competitor", entity_type="competitor")
    db.add_all([pir, dlf, old])
    db.add_all([SeededEntity(client_id=c.id, entity_id=pir.id, kind="executive", name="Pirojsha Godrej", rank=1, status="active", validated=True),
                SeededEntity(client_id=c.id, entity_id=dlf.id, kind="competitor", name="DLF", rank=1, context_term="real estate", status="active", validated=True)])
    db.commit()
    specs = [s for s in build_queries(db, c.id) if s.seeded]
    by = {(s.entity_name, s.kind): s for s in specs}
    assert by[("Pirojsha Godrej", "executive")].google_news == '"Pirojsha Godrej" "Godrej Properties"'
    assert by[("DLF", "competitor")].google_news == '"DLF" real estate' and "Godrej" not in by[("DLF", "competitor")].google_news
    assert all(s.youtube == "" for s in specs)                                       # no per-entity social
    assert "fraud" in by[("DLF", "seed_risk")].google_news
    names = {s.entity_name for s in build_queries(db, c.id)}
    assert "Plain Competitor" not in names                                           # competitors stay off unless seeded


def test_backfill_stops_a_seeded_entity_at_its_cap_and_skips_the_rest(db, monkeypatch):
    from app.services.backfill import engine as bf
    from app.services.seeding import settings as seed_settings
    monkeypatch.setattr(seed_settings, "EXEC_BACKFILL_CAP", 60)
    c, brand = _client(db)
    pir = Entity(id=uuid.uuid4(), client_id=c.id, name="Pirojsha Godrej", entity_type="person")
    db.add(pir)
    db.add(SeededEntity(client_id=c.id, entity_id=pir.id, kind="executive", name="Pirojsha Godrej", rank=1, status="active", validated=True,
                        seeded_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)))
    db.commit()
    fetched = []

    def fetch(query, s, e, ctx):
        fetched.append(query)
        return [{"i": n} for n in range(30)]

    def ingest(db_, client_id, src, raw, **kw):
        return {"saved": len(raw), "deduped": 0, "skipped_undated": 0, "dropped_irrelevant": 0}

    cfg = bf.BackfillConfig(sources=("google_news",), max_slices_per_run=50, relevance_filter=False)
    summary = bf.run_client(db, c.id, cfg, fetchers={"google_news": fetch}, ingest=ingest)
    saved = sum(r.new_count or 0 for r in db.query(BackfillSlice).filter(BackfillSlice.entity_id == pir.id))
    assert 60 <= saved <= 60 + 29                                                    # stops once the cap is reached (one slice of overshoot at most)
    pir_pending = db.query(BackfillSlice).filter(BackfillSlice.entity_id == pir.id, BackfillSlice.status == "PENDING").count()
    assert pir_pending == 0 and db.query(BackfillSlice).filter(BackfillSlice.entity_id == pir.id, BackfillSlice.status == "SKIPPED").count() > 0
    assert any("fraud" in q or "court" in q for q in fetched[:2])                    # risk-worded slice first


def test_backfill_limits_seeded_slices_to_the_last_24_months(db):
    from app.services.backfill.engine import BackfillConfig, plan_slices
    from app.services.backfill.queries import QuerySpec
    spec = QuerySpec("executive", "e1", "X Y", '"X Y"', "", '"X Y"', "X Y", seeded=True)
    other = QuerySpec("executive", "e2", "P Q", '"P Q"', '"P Q"', '"P Q"', "P Q")
    cfg = BackfillConfig(sources=("google_news",), end=dt.date(2026, 11, 4))
    seeded_plan = [p for p in plan_slices([spec], cfg)]
    plain_plan = [p for p in plan_slices([other], cfg)]
    assert min(p.start for p in seeded_plan) >= dt.date(2024, 10, 1)
    assert min(p.start for p in plain_plan) == dt.date(2015, 1, 1)


# --------------------------------------------------------------------------------------- per-run cap
def test_run_pipeline_collects_at_most_25_new_documents_from_a_seeded_feed_and_all_from_the_others(db, monkeypatch):
    import app.workers.aggregation_tasks as agg
    import app.adapters.registry as registry
    import app.services.document_service as docsvc
    import app.workers.collection_tasks as ct
    from app.services.client_service import provision_entity_search_feeds

    c, brand = _client(db)
    dlf = Entity(id=uuid.uuid4(), client_id=c.id, name="DLF", entity_type="competitor")
    db.add(dlf)
    db.add(SeededEntity(client_id=c.id, entity_id=dlf.id, kind="competitor", name="DLF", rank=1, context_term="real estate", status="active", validated=True))
    db.commit()
    seeded_feeds = provision_entity_search_feeds(db, c.id, "DLF", co_occur_with="real estate", quote=True, co_quoted=False)
    plain_feed = RSSFeed(feed_name="Brand Google News Feed", feed_url="https://news.google.com/rss/search?q=Godrej", client_id=c.id, is_active=True,
                         source_type="entity_search", source_format="rss")
    db.add(plain_feed)
    db.commit()

    class FakeAdapter:
        def fetch(self, url):
            return [{"link": f"{url}#{i}"} for i in range(40)]

        def normalize(self, entry, source_id):
            return {"url": entry["link"], "title": "t", "content": "c", "published_at": dt.datetime.now(dt.timezone.utc), "source_id": source_id}

    saved_by_url = {}

    def fake_save(db_, norm_doc):
        key = norm_doc.url.split("#")[0]
        saved_by_url[key] = saved_by_url.get(key, 0) + 1
        return True, None, None

    monkeypatch.setitem(registry.ADAPTER_REGISTRY, "rss", FakeAdapter)
    monkeypatch.setitem(registry.ADAPTER_REGISTRY, "gdelt_json", FakeAdapter)
    monkeypatch.setitem(registry.ADAPTER_REGISTRY, "hn_algolia_json", FakeAdapter)
    monkeypatch.setattr(docsvc, "process_and_save_document", fake_save)
    monkeypatch.setattr(ct, "_get_or_create_source", lambda db_, feed: SimpleNamespace(id=uuid.uuid4()))
    for name in ("_stage_collect_youtube", "_stage_collect_instagram", "_stage_collect_reddit"):
        monkeypatch.setattr(agg, name, lambda *a, **k: [])
    monkeypatch.setattr(agg, "_stale_pending_search_doc_ids", lambda *a, **k: [])
    from app.schemas import document as docschema
    monkeypatch.setattr(docschema, "NormalizedDocument", lambda **kw: SimpleNamespace(**kw))

    ctx = SimpleNamespace(client_id=c.id, run_id="r1", worker_id="w1")
    agg._stage_collect(ctx, db)
    for f in seeded_feeds:
        assert saved_by_url[f.feed_url] == 25
    assert saved_by_url[plain_feed.feed_url] == 40
    assert db.query(RSSFeed).filter(RSSFeed.last_polled_at.isnot(None)).count() == 4        # last_polled_at is stamped for every feed polled


# ---------------------------------------------------------------------------------- selection by rule (build_plan)
def _cand(name, slot, urls=("https://news.example.com/x",)):
    return {"name": name, "slot": slot, "role": slot, "source_urls": list(urls)}


def _count_fetch(counts):
    """fetch(query, a, b) -> n items per slice, keyed by the person/company name inside the query."""
    def fetch(query, a, b):
        for name, n in counts.items():
            if f'"{name}"' in query:
                return [object()] * n
        return []
    return fetch


def _proposal(execs, comps=(), company=None):
    return {"company": company or {"website": None, "primary_market": "India"}, "executives": list(execs), "competitors": list(comps),
            "cost_usd": 0.014, "citations": ["https://c.example.com"], "model": proposer.MODEL}


def test_executives_are_chosen_by_role_order_then_news_count_and_directors_only_fill_what_management_leaves(db):
    c, brand = _client(db)
    execs = [_cand("Dir Z", "director"), _cand("Mgmt Low", "management"), _cand("Mgmt High", "management"), _cand("Cfo P", "cfo"),
             _cand("Founder F", "founder"), _cand("Chair C", "chairperson"), _cand("Ceo O", "md_ceo"), _cand("Mgmt Mid", "management")]
    counts = {"Dir Z": 90, "Mgmt Low": 5, "Mgmt High": 60, "Cfo P": 4, "Founder F": 7, "Chair C": 3, "Ceo O": 8, "Mgmt Mid": 20}
    plan = service.build_plan(db, c.id, propose_fn=lambda *a, **k: _proposal(execs), fetch=_count_fetch({k: n for k, n in counts.items()}),
                              measure_aliases=False, fetch_text=_no_page)
    chosen = [x["name"] for x in plan["executives"] if x["selected"]]
    # per-slice counts above are x4 over the four slices; role order first: chair, CEO, CFO, founder, then the best management by count
    assert chosen == ["Chair C", "Ceo O", "Cfo P", "Founder F", "Mgmt High"]
    assert "Dir Z" not in chosen                                       # 90 news items, but a director only fills a free slot
    only_mgmt = [_cand("Chair C", "chairperson"), _cand("Dir Z", "director"), _cand("Dir Y", "director")]
    plan2 = service.build_plan(db, c.id, propose_fn=lambda *a, **k: _proposal(only_mgmt), fetch=_count_fetch({"Chair C": 3, "Dir Z": 4, "Dir Y": 9}),
                               measure_aliases=False, fetch_text=_no_page)
    assert [x["name"] for x in plan2["executives"] if x["selected"]] == ["Chair C", "Dir Y", "Dir Z"]   # directors fill the open slots, best count first


def test_the_chosen_list_does_not_depend_on_the_order_or_extra_candidates_in_the_answer(db):
    c, brand = _client(db)
    base = [_cand("Chair C", "chairperson"), _cand("Ceo O", "md_ceo"), _cand("Cfo P", "cfo"), _cand("Mgmt A", "management"), _cand("Mgmt B", "management")]
    counts = {"Chair C": 9, "Ceo O": 9, "Cfo P": 9, "Mgmt A": 30, "Mgmt B": 20, "Extra Low": 2, "Extra Dir": 70}
    fetch = _count_fetch(counts)

    def chosen(execs):
        plan = service.build_plan(db, c.id, propose_fn=lambda *a, **k: _proposal(execs), fetch=fetch, measure_aliases=False, fetch_text=_no_page)
        return [x["name"] for x in plan["executives"] if x["selected"]]

    a = chosen(base)
    b = chosen(list(reversed(base)))
    c_ = chosen(base + [_cand("Extra Low", "management"), _cand("Extra Dir", "director")])     # a different run adds two candidates
    assert a == b == c_ == ["Chair C", "Ceo O", "Cfo P", "Mgmt A", "Mgmt B"]


def test_competitors_ownership_rejections_need_a_confirming_page_otherwise_the_candidate_is_kept_with_a_note(db):
    c, brand = _client(db, "EaseMyTrip", "easemytrip.com")
    gb, ix = "https://en.wikipedia.org/wiki/Goibibo", "https://example.com/ixigo-story"
    comps = [
        {"name": "MakeMyTrip", "context_term": "online travel", "hq_country": "India", "source_urls": []},
        {"name": "Goibibo", "context_term": "online travel", "hq_country": "India", "parent_company": "MakeMyTrip", "source_urls": [gb]},
        {"name": "ixigo", "context_term": "online travel", "hq_country": "India", "parent_company": "MakeMyTrip", "source_urls": [ix], "exchange_listed": True},
        {"name": "Expedia", "context_term": "online travel", "hq_country": "USA", "india_operations": "minor", "source_urls": []},
        {"name": "Skyscanner", "context_term": "online travel", "hq_country": "United Kingdom", "parent_company": "Booking Holdings", "source_urls": []},
        {"name": "Cleartrip", "context_term": "online travel", "hq_country": "India", "source_urls": []},
        {"name": "EaseMyTrip Mobility", "context_term": "online travel", "hq_country": "India", "source_urls": []},
        {"name": "Thin Peer", "context_term": "online travel", "hq_country": "India", "source_urls": []},
    ]
    counts = {"MakeMyTrip": 12, "Goibibo": 99, "ixigo": 8, "Expedia": 99, "Skyscanner": 30, "Cleartrip": 9, "EaseMyTrip Mobility": 50, "Thin Peer": 1}
    pages = {gb: "Goibibo is a wholly owned subsidiary of MakeMyTrip Limited.", ix: "MakeMyTrip sold its stake in ixigo in 2021."}
    plan = service.build_plan(db, c.id, propose_fn=lambda *a, **k: _proposal([], comps, {"primary_market": "India", "parent_company": None}),
                              fetch=_count_fetch(counts), measure_aliases=False, fetch_text=lambda u: pages.get(u))
    by = {x["name"]: x for x in plan["competitors"]}
    g = by["Goibibo"]["validation"]
    assert not g["accepted"] and "subsidiary of another candidate" in g["reason"] and f"confirmed on {gb}" in g["reason"]       # verified: rejected
    i = by["ixigo"]
    assert i["validation"]["accepted"] and any("ownership claim unverified" in n for n in i["validation"]["notes"])           # unverified: kept, with the note
    assert "not in India" in by["Skyscanner"]["validation"]["reason"] or "not in India" in by["Expedia"]["validation"]["reason"]
    assert "not in India" in by["Expedia"]["validation"]["reason"] and "not in India" in by["Skyscanner"]["validation"]["reason"]  # outside the primary market
    assert "same group" in by["EaseMyTrip Mobility"]["validation"]["reason"]
    assert "sector count 4" in by["Thin Peer"]["validation"]["reason"]
    assert {x["name"] for x in plan["competitors"] if x["selected"]} == {"MakeMyTrip", "Cleartrip", "ixigo"}                # Goibibo, Expedia, Skyscanner out; ixigo in


def test_a_withdrawn_ownership_claim_is_not_used_to_reject(db):
    c, brand = _client(db, "EaseMyTrip", "easemytrip.com")
    comps = [{"name": "MakeMyTrip", "context_term": "online travel", "hq_country": "India", "source_urls": []},
             {"name": "ixigo", "context_term": "online travel", "hq_country": "India", "parent_company": "MakeMyTrip", "source_urls": ["https://x.example/ix"]}]
    prop = _proposal([], comps, {"primary_market": "India"})
    prop["ownership_evidence"] = [{"candidate": "ixigo", "child": "ixigo", "parent": "MakeMyTrip", "still_owned": False, "source_urls": []}]
    plan = service.build_plan(db, c.id, propose_fn=lambda *a, **k: prop, fetch=_count_fetch({"MakeMyTrip": 12, "ixigo": 8}), measure_aliases=False,
                              fetch_text=lambda u: "ixigo is owned by MakeMyTrip" if "ix" in u else None)
    ix = {x["name"]: x for x in plan["competitors"]}["ixigo"]
    assert ix["validation"]["accepted"] and any("withdrawn" in n for n in ix["validation"]["notes"])


def test_competitors_rank_by_tracked_then_answers_naming_them_then_model_position_then_news_count_and_ignore_the_listed_flag():
    def it(name, n, tracked=False, seen=1, pos=(1,), listed=False):
        return {"name": name, "tracked": tracked, "seen_in": seen, "positions": list(pos), "validation": {"accepted": True, "pair_count_24m": n, "listed": listed}}
    items = [it("Big count only", 900), it("Listed only", 500, listed=True), it("Named by 3", 30, seen=3, pos=(5, 6, 4)), it("Named by 3 earlier", 25, seen=3, pos=(2, 3, 2)),
             it("Named by 2", 400, seen=2, pos=(1, 1)), it("Tracked thin", 21, tracked=True, seen=1, pos=(8,)), it("Tracked agreed", 22, tracked=True, seen=3, pos=(3, 3, 3))]
    order = [x["name"] for x in validator.rank_competitors(items)]
    assert order == ["Tracked agreed", "Tracked thin", "Named by 3 earlier", "Named by 3", "Named by 2", "Big count only", "Listed only"]
    # count decides only as the last key; no 20% band: a far lower count still ranks above when everything before ties
    assert [x["name"] for x in validator.rank_competitors([it("A", 100), it("B", 79)])] == ["A", "B"]
    assert [x["name"] for x in validator.rank_competitors([it("A", 79, pos=(2,)), it("B", 100, pos=(3,))])] == ["A", "B"]      # model position beats count


def test_merge_counts_how_many_answers_name_a_company_and_where_name_variants_included():
    def ans(*names):
        return {"company": {}, "executives": [], "competitors": [{"name": n, "context_term": "x"} for n in names], "cost_usd": 0.01, "citations": ["u"]}
    a = ans("DLF", "Brigade Group", "Oberoi Realty")
    b = ans("Oberoi Realty", "Brigade Enterprises", "Brigade Group", "DLF Limited")       # Brigade appears twice in this answer: counts once
    fu = ans("DLF")
    m = proposer.merge_proposals([a, b, fu])
    by = {c["name"]: c for c in m["competitors"]}
    assert by["DLF"]["seen_in"] == 3 and sorted(by["DLF"]["positions"]) == [1, 1, 4]
    assert by["Brigade Group"]["seen_in"] == 2 and by["Oberoi Realty"]["seen_in"] == 2
    assert len(m["competitors"]) == 3 and m["calls"] == 3
    again = proposer.merge_proposals([m, ans("Oberoi Realty")])                           # counters survive a second merge
    assert {c["name"]: c["seen_in"] for c in again["competitors"]}["Oberoi Realty"] == 3


def test_selection_uses_agreement_not_the_listed_flag_or_the_count_beyond_the_minimum(db):
    c, brand = _client(db)
    db.add(Entity(id=uuid.uuid4(), client_id=c.id, name="Lodha", entity_type="competitor"))
    db.commit()
    comps = [
        {"name": "Huge Count Realty", "context_term": "real estate", "hq_country": "India", "exchange_listed": True, "seen_in": 1, "positions": [8]},
        {"name": "Lodha Group", "context_term": "real estate", "hq_country": "India", "exchange_listed": False, "seen_in": 3, "positions": [2, 2, 2]},
        {"name": "Agreed Realty", "context_term": "real estate", "hq_country": "India", "exchange_listed": False, "seen_in": 3, "positions": [1, 1, 1]},
        {"name": "Thin Realty", "context_term": "real estate", "hq_country": "India", "seen_in": 3, "positions": [3, 3, 3]},
    ]
    prop = _proposal([], comps, {"primary_market": "India"})
    prop["calls"] = 3
    plan = service.build_plan(db, c.id, propose_fn=lambda *a, **k: prop, fetch=_count_fetch({"Huge Count Realty": 99, "Lodha Group": 6, "Agreed Realty": 7, "Thin Realty": 1}), measure_aliases=False)
    chosen = [x["name"] for x in plan["competitors"] if x["selected"]]
    assert chosen == ["Lodha Group", "Agreed Realty", "Huge Count Realty"]          # tracked first, then agreement; Thin Realty is below the 20 minimum
    assert not {x["name"]: x for x in plan["competitors"]}["Thin Realty"]["validation"]["accepted"]


def test_group_guard_reports_name_based_and_model_claimed_relations():
    info = {"parent_company": "Orbit Holdings Group", "group_companies": ["Zenith Capital", "Zenith Agro"], "primary_market": "India"}
    g = validator.group_conflict
    assert "shares its name" in g({"name": "Acme Foods"}, "Acme Realty", info, [])                       # sister company (Godrej Consumer vs Godrej Properties)
    assert "parent company" in g({"name": "Orbit Holdings Group"}, "Acme Realty", info, [])
    assert "sister/group" in g({"name": "Zenith Capital"}, "Acme Realty", info, [])
    assert "client's group" in g({"name": "Some Subsidiary", "parent_company": "Orbit Holdings"}, "Acme Realty", info, [])
    assert "parent of the client" in g({"name": "Holding Co", "subsidiaries": ["Acme Realty"]}, "Acme Realty", info, [])
    assert g({"name": "DLF", "parent_company": "DLF Group"}, "Acme Realty", info, ["DLF", "Lodha"]) is None
    assert "subsidiary of another" in g({"name": "Goibibo", "parent_company": "MakeMyTrip"}, "EaseMyTrip", {}, ["MakeMyTrip", "Goibibo"])
    kinds = {c["basis"] for c in validator.ownership_claims({"name": "Goibibo", "parent_company": "MakeMyTrip"}, "EaseMyTrip", {}, ["MakeMyTrip"])}
    assert kinds == {"model"}                                                                       # a model claim, which must be verified before it rejects
    assert {c["basis"] for c in validator.ownership_claims({"name": "Acme Foods"}, "Acme Realty", {}, [])} == {"name"}


def test_ownership_needs_a_fetched_page_with_both_names_and_an_ownership_phrase_in_the_right_order():
    c = validator.ownership_confirmed_on_page
    assert c("Goibibo is a wholly owned subsidiary of MakeMyTrip Limited.", "Goibibo", "MakeMyTrip")
    assert c("Goibibo, owned by MakeMyTrip, said", "Goibibo", "MakeMyTrip") and c("Redbus was acquired by MakeMyTrip in 2024", "redBus", "MakeMyTrip")
    assert not c("MakeMyTrip is owned by Trip.com. Goibibo is a travel site.", "Goibibo", "MakeMyTrip")        # not about this pair
    assert not c("MakeMyTrip sold its stake; ixigo is independent.", "ixigo", "MakeMyTrip")                     # both names, no ownership phrase
    assert not c("MakeMyTrip was acquired by Trip.com", "Goibibo", "MakeMyTrip")
    assert validator.verify_ownership("Goibibo", "MakeMyTrip", ["https://a.example/x", "https://b.example/y"],
                                      lambda u: "Goibibo is owned by MakeMyTrip" if u.endswith("y") else None) == "https://b.example/y"
    assert validator.verify_ownership("Goibibo", "MakeMyTrip", ["https://a.example/x"], lambda u: None) is None


# ------------------------------------------------------------------------------------------- website (step 5)
def _http(status=200, url="https://www.godrejproperties.com/", text="<title>Godrej Properties</title>"):
    return lambda u, **k: SimpleNamespace(status_code=status, url=url, text=text, headers={})


def test_website_must_resolve_and_match_the_company_name():
    ok = validator.verify_website("https://www.godrejproperties.com", "Godrej Properties", _http())
    assert ok["ok"] and ok["domain"] == "godrejproperties.com"
    assert not validator.verify_website("https://www.godrejproperties.com", "Godrej Properties", _http(status=404))["ok"]
    assert not validator.verify_website("https://spam.example.org", "Godrej Properties", _http(url="https://spam.example.org/", text="buy pills"))["ok"]
    assert validator.verify_website("https://corp.example.in", "Godrej Properties", _http(url="https://corp.example.in/", text="Welcome to Godrej Properties Ltd"))["ok"]
    assert not validator.verify_website(None, "Godrej Properties")["ok"]

    def boom(u, **k):
        raise ConnectionError("dns")
    assert not validator.verify_website("https://nope.invalid", "X Y", boom)["ok"]


def test_apply_sets_the_verified_website_on_the_brand_only_when_empty_and_the_rule_then_uses_it(db, monkeypatch):
    monkeypatch.setattr(service, "_refresh_matcher_and_rematch", lambda *a, **k: None)
    c, brand = _client(db, domain=None)
    prop = _proposal([_cand("Pirojsha Godrej", "chairperson", ("https://www.godrejproperties.com/leadership",))], [],
                     {"website": "https://www.godrejproperties.com", "primary_market": "India"})
    fetch = _count_fetch({"Pirojsha Godrej": 0})                                  # no news at all
    out = service.seed_client(db, c.id, apply=False, propose_fn=lambda *a, **k: prop, fetch=fetch, measure_aliases=False, fetch_text=_no_page, http_get=_http())
    assert out["plan"]["website"]["ok"] and out["plan"]["executives"][0]["validation"]["official_sources"]      # the verified domain is used by the rule
    assert not out["plan"]["executives"][0]["validation"]["accepted"]                                         # but no news item: still needs_review
    prop2 = _proposal([_cand("Pirojsha Godrej", "chairperson")], [], {"website": "https://www.godrejproperties.com", "primary_market": "India"})
    service.seed_client(db, c.id, apply=True, propose_fn=lambda *a, **k: prop2, fetch=_count_fetch({"Pirojsha Godrej": 5}), measure_aliases=False, fetch_text=_no_page, http_get=_http())
    db.refresh(brand)
    assert brand.domain == "godrejproperties.com" and brand.website == "https://godrejproperties.com"
    # a stored domain is never overwritten
    c2, brand2 = _client(db, "Other Co", "stored.example.com")
    prop3 = _proposal([_cand("A B", "chairperson")], [], {"website": "https://www.godrejproperties.com", "primary_market": "India"})
    service.seed_client(db, c2.id, apply=True, propose_fn=lambda *a, **k: prop3, fetch=_count_fetch({"A B": 5}), measure_aliases=False, fetch_text=_no_page, http_get=_http())
    db.refresh(brand2)
    assert brand2.domain == "stored.example.com"


# ------------------------------------------------------------------------------------- seed-scoped rematch (step 6)
def _rematch_setup(db):
    from app.services.seeding import rematch  # noqa: F401
    c, brand = _client(db)
    pir = Entity(id=uuid.uuid4(), client_id=c.id, name="Pirojsha Godrej", entity_type="person")
    dlf = Entity(id=uuid.uuid4(), client_id=c.id, name="DLF", entity_type="competitor")
    other = Entity(id=uuid.uuid4(), client_id=c.id, name="Not Seeded", entity_type="person")
    db.add_all([pir, dlf, other])
    db.add_all([EntityKeyword(entity_id=pir.id, keyword_text="Pirojsha Godrej", match_type="exact", category="PRIMARY", priority=1, is_active=True),
                EntityKeyword(entity_id=dlf.id, keyword_text="DLF", match_type="exact", category="PRIMARY", priority=1, is_active=True),
                EntityKeyword(entity_id=other.id, keyword_text="Not Seeded", match_type="exact", category="PRIMARY", priority=1, is_active=True)])
    db.add_all([SeededEntity(client_id=c.id, entity_id=pir.id, kind="executive", name="Pirojsha Godrej", rank=1, status="active", validated=True),
                SeededEntity(client_id=c.id, entity_id=dlf.id, kind="competitor", name="DLF", rank=1, context_term="real estate", status="active", validated=True)])
    docs = {}
    for key, title, body, with_brand in [
        ("a", "Pirojsha Godrej on the new launch", "x", True),
        ("b", "Godrej Properties results", "Chairman Pirojsha Godrej said", True),
        ("c", "Quarterly note", "nothing here", True),
        ("d", "DLF launches a tower", "the real estate major", True),
        ("e", "DLF dividend", "no sector words", True),                       # one-word name, no context word: not matched
        ("f", "Pirojsha Godrej at a conference", "x", False),                  # does not mention the client: not visible
        ("g", "Not Seeded appears", "x", True),                                # an unseeded entity must not be touched
    ]:
        d = Document(id=uuid.uuid4(), url=f"http://t.test/{key}", title=title, normalized_content=body, published_at=dt.datetime.now(dt.timezone.utc))
        db.add(d)
        db.flush()
        docs[key] = d
        if with_brand:
            db.add(EntityMention(document_id=d.id, entity_id=brand.id, mention_count=1))
    db.add(EntityMention(document_id=docs["a"].id, entity_id=pir.id, mention_count=1))        # already mentioned
    db.commit()
    return c, pir, dlf, other, docs


def test_seed_scoped_rematch_matches_all_visible_documents_and_writes_only_for_the_seeded_entities(db):
    from app.models.document import DocumentMatch
    from app.services.seeding import rematch
    c, pir, dlf, other, docs = _rematch_setup(db)
    before_other = db.query(EntityMention).filter(EntityMention.entity_id == other.id).count()
    out = rematch.rematch_seeded(db, c.id, [pir.id, dlf.id])
    assert out["Pirojsha Godrej"] == {"matched_docs": 2, "already_had": 1, "new_mentions": 1, "new_matches": 2}       # a (had) + b; f is not visible
    assert out["DLF"]["matched_docs"] == 1 and out["DLF"]["new_mentions"] == 1                                       # d only: e lacks a sector word
    assert {m.document_id for m in db.query(EntityMention).filter(EntityMention.entity_id == dlf.id)} == {docs["d"].id}
    assert db.query(DocumentMatch).filter(DocumentMatch.matched_entity_id == pir.id, DocumentMatch.match_type == "seeded_rematch").count() == 2
    assert db.query(EntityMention).filter(EntityMention.entity_id == other.id).count() == before_other                  # untouched
    again = rematch.rematch_seeded(db, c.id, [pir.id, dlf.id])                                                           # safe to re-run
    assert again["Pirojsha Godrej"]["new_mentions"] == 0 and again["Pirojsha Godrej"]["new_matches"] == 0 and again["DLF"]["new_mentions"] == 0


def test_rematch_preview_is_read_only_and_reports_what_would_be_gained(db):
    from app.services.seeding import rematch
    c, pir, dlf, other, docs = _rematch_setup(db)
    plan = {"executives": [{"name": "Pirojsha Godrej", "selected": True, "aliases": []}],
            "competitors": [{"name": "DLF", "selected": True, "aliases": [], "context_term": "real estate"},
                            {"name": "Unselected Co", "selected": False, "aliases": []}]}
    mentions_before = db.query(EntityMention).count()
    out = rematch.preview_plan(db, c.id, plan)
    assert out["Pirojsha Godrej"]["new_mentions"] == 1 and out["DLF"]["new_mentions"] == 1 and "Unselected Co" not in out
    assert db.query(EntityMention).count() == mentions_before


def test_apply_runs_the_rematch_and_reports_the_gain_per_entity(db, monkeypatch):
    monkeypatch.setattr(service, "_refresh_matcher_and_rematch", lambda *a, **k: None)
    c, brand = _client(db)
    for i in range(3):
        d = Document(id=uuid.uuid4(), url=f"http://t.test/p{i}", title="Pirojsha Godrej of Godrej Properties", normalized_content="x", published_at=dt.datetime.now(dt.timezone.utc))
        db.add(d)
        db.flush()
        db.add(EntityMention(document_id=d.id, entity_id=brand.id, mention_count=1))
    db.commit()
    prop = _proposal([_cand("Pirojsha Godrej", "chairperson")], [], {"primary_market": "India"})
    out = service.seed_client(db, c.id, apply=True, propose_fn=lambda *a, **k: prop, fetch=_count_fetch({"Pirojsha Godrej": 5}), measure_aliases=False, fetch_text=_no_page)
    assert out["applied"]["rematch"]["Pirojsha Godrej"]["new_mentions"] == 3
    ent = db.query(Entity).filter(Entity.name == "Pirojsha Godrej").one()
    assert db.query(EntityMention).filter(EntityMention.entity_id == ent.id).count() == 3


# ------------------------------------------------------------------------- union of several answers (stability)
def test_same_company_merges_name_variants_but_not_sister_companies():
    sc = validator.same_company
    assert sc("Prestige Group", "Prestige Estates Projects Limited") and sc("Yatra.com", "Yatra Online Limited") and sc("MakeMyTrip", "MakeMyTrip Limited")
    assert sc("DLF", "DLF Limited") and sc("Oberoi", "Oberoi Realty") and sc("Brigade Group", "Brigade Enterprises")
    assert not sc("Reliance Retail", "Reliance Industries") and not sc("Tata Group", "Tata Power") and not sc("Lodha", "Mahindra Lifespace Developers")


def test_merge_proposals_pools_candidates_so_one_answer_missing_someone_does_not_change_the_list():
    a = {"company": {"website": "https://x.com", "primary_market": ""}, "cost_usd": 0.02, "citations": ["u1"], "model": "m",
         "executives": [{"name": "Rajesh Adani", "slot": "management", "source_urls": ["https://a"]}, {"name": "Jeet Adani", "slot": "management", "source_urls": []}],
         "competitors": [{"name": "Prestige Group", "context_term": "real estate", "hq_country": "India", "source_urls": []}]}
    b = {"company": {"primary_market": "India"}, "cost_usd": 0.03, "citations": ["u2"], "model": "m",
         "executives": [{"name": "Jugeshinder Singh", "slot": "cfo", "source_urls": ["https://b"]}, {"name": "Rajesh Adani", "slot": "md_ceo", "source_urls": ["https://c"]}],
         "competitors": [{"name": "Prestige Estates Projects Limited", "parent_company": "", "subsidiaries": ["X"], "source_urls": ["https://d"]}]}
    m = proposer.merge_proposals([a, b])
    assert m["cost_usd"] == pytest.approx(0.05) and m["company"] == {"website": "https://x.com", "primary_market": "India"} and m["calls"] == 2
    ex = {e["name"]: e for e in m["executives"]}
    assert set(ex) == {"Rajesh Adani", "Jeet Adani", "Jugeshinder Singh"}
    assert ex["Rajesh Adani"]["slot"] == "md_ceo" and ex["Rajesh Adani"]["source_urls"] == ["https://a", "https://c"]       # most senior slot, pooled sources
    assert len(m["competitors"]) == 1 and m["competitors"][0]["subsidiaries"] == ["X"] and m["competitors"][0]["hq_country"] == "India"
    assert m == proposer.merge_proposals([b, a]) or {e["name"] for e in proposer.merge_proposals([b, a])["executives"]} == set(ex)


def test_propose_multi_makes_the_requested_number_of_web_calls_and_any_failure_aborts():
    calls = []

    def post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _Resp(200, _ok_payload(content='{"company":{},"executives":{"chairperson":{"name":"Chair C","source_urls":["https://x"]}},"competitors":[]}'))

    out = proposer.propose_multi("X", calls=2, post=post, api_key="k")
    # two pooled calls, plus the one follow-up because the md_ceo / cfo / founder slots are empty in these answers
    assert len(calls) == 3 and all("plugins" in c for c in calls) and out["calls"] == 3 and out["cost_usd"] == pytest.approx(0.0423)
    n = {"i": 0}

    def flaky(url, headers=None, json=None, timeout=None):
        n["i"] += 1
        return _Resp(200, _ok_payload()) if n["i"] == 1 else _Resp(500)

    with pytest.raises(SeedingAborted):
        proposer.propose_multi("X", calls=2, post=flaky, api_key="k")


# ------------------------------------------------------------------------------- PDF verification (pypdf)
def _pdf_bytes(pages):
    """A minimal valid PDF with one line of text per page."""
    objs = []                                           # 1-based object bodies
    n_pages = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objs.append("<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>")
    font_id = 3 + 2 * n_pages
    for i, text in enumerate(pages):
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents {4 + 2 * i} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>")
        stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


class _PdfResp:
    def __init__(self, body, status=200, length=None):
        self.status_code = status
        self.content = body
        self.headers = {"content-length": str(length if length is not None else len(body))}

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]


def test_pdf_text_is_read_from_the_first_ten_pages_only():
    pages = [f"filler page {i}" for i in range(11)]
    pages[1] = "Rajendra Khetawat Chief Financial Officer"
    pages[10] = "Late Person Name"
    get = lambda url, **k: _PdfResp(_pdf_bytes(pages))                      # noqa: E731
    text = validator.fetch_pdf_text("https://www.nseindia.com/a.pdf", get)
    assert "Rajendra Khetawat" in text and "Late Person Name" not in text                 # page 11 is past the 10-page cap


def test_pdf_over_five_megabytes_or_not_a_pdf_or_slow_or_broken_is_not_read():
    big_declared = lambda url, **k: _PdfResp(_pdf_bytes(["x"]), length=6 * 1024 * 1024)        # noqa: E731
    assert validator.fetch_pdf_text("https://www.nseindia.com/a.pdf", big_declared) is None
    big_actual = lambda url, **k: _PdfResp(b"%PDF-1.4" + b"0" * (5 * 1024 * 1024 + 10), length=100)       # noqa: E731
    assert validator.fetch_pdf_text("https://www.nseindia.com/a.pdf", big_actual) is None
    assert validator.fetch_pdf_text("https://www.nseindia.com/a.pdf", lambda url, **k: _PdfResp(b"<html>not a pdf</html>")) is None
    assert validator.fetch_pdf_text("https://www.nseindia.com/a.pdf", lambda url, **k: _PdfResp(b"%PDF-1.4 garbage")) is None
    assert validator.fetch_pdf_text("https://www.nseindia.com/a.pdf", lambda url, **k: _PdfResp(b"", status=404)) is None

    def boom(url, **k):
        raise TimeoutError("slow")
    assert validator.fetch_pdf_text("https://www.nseindia.com/a.pdf", boom) is None
    clock = iter([0.0, 100.0, 200.0, 300.0, 400.0, 500.0])
    import time as _t
    orig = _t.monotonic
    _t.monotonic = lambda: next(clock, 999.0)
    try:
        assert validator.fetch_pdf_text("https://www.nseindia.com/a.pdf", lambda url, **k: _PdfResp(_pdf_bytes(["x"] * 3)), timeout=20) is None   # over the time budget
    finally:
        _t.monotonic = orig


def test_a_pdf_is_opened_only_on_the_company_domain_or_nse_bse():
    f = validator.pdf_allowed
    assert f("https://www.nseindia.com/x.pdf", [], None) and f("https://www.bseindia.com/x.pdf", [], None)
    assert f("https://www.godrejproperties.com/ar.pdf", [], "Godrej Properties") and f("https://ir.example.in/a.pdf", ["example.in"], None)
    assert not f("https://gplwebsitecdnblob.blob.core.windows.net/godrej-cdn/ar.pdf", [], "Godrej Properties")     # a CDN host is not the company domain
    assert not f("https://news.example.com/a.pdf", [], "Godrej Properties") and not f("https://www.sebi.gov.in/a.pdf", [], None)
    assert validator.fetch_page_text("https://news.example.com/a.pdf", allow_pdf=False) is None


def test_an_executive_with_one_or_two_news_items_is_verified_by_a_pdf_on_nse_and_labelled_so(monkeypatch):
    opened = []
    monkeypatch.setattr(validator, "fetch_pdf_text", lambda url, *a, **k: (opened.append(url), "Chief Financial Officer: Rajendra Khetawat")[1])
    who = {"name": "Rajendra Khetawat", "slot": "cfo", "role": "Chief Financial Officer"}
    base = {**who, "source_urls": ["https://nsearchives.nseindia.com/c/GODREJPROP_kmp.pdf"]}
    two = lambda q, a, b, n=iter([1, 1, 0, 0]): [object()] * next(n)                                         # noqa: E731
    ok = validator.validate_executive(base, "Godrej Properties", [], two)
    assert ok["accepted"] and ok["method"] == "PDF (exchange filing)" and opened == [base["source_urls"][0]]
    # the same name on a PDF behind a CDN host is never opened -> needs_review
    opened.clear()
    cdn = {**who, "source_urls": ["https://gplwebsitecdnblob.blob.core.windows.net/godrej-cdn/ar.pdf"]}
    no = validator.validate_executive(cdn, "Godrej Properties", [], lambda q, a, b, n=iter([1, 1, 0, 0]): [object()] * next(n))
    assert not no["accepted"] and opened == [] and no["needs_better_sources"]
    # an unreadable PDF keeps him in needs_review
    monkeypatch.setattr(validator, "fetch_pdf_text", lambda url, *a, **k: None)
    unread = validator.validate_executive(base, "Godrej Properties", [], lambda q, a, b, n=iter([1, 1, 0, 0]): [object()] * next(n))
    assert not unread["accepted"] and unread["needs_better_sources"]


def test_verification_method_labels():
    m = validator.verification_method
    assert m("https://www.godrejproperties.com/a.pdf", [], "Godrej Properties") == "PDF (company domain)"
    assert m("https://nsearchives.nseindia.com/a.pdf", [], "X Y") == "PDF (exchange filing)"
    assert m("https://www.bseindia.com/a.html", [], "X Y") == "exchange filing"
    assert m("https://www.godrejproperties.com/leadership", [], "Godrej Properties") == "company page"
    assert m("https://news.example.com/a", [], "Godrej Properties") == "cited page"


# --------------------------------------------------------------------------- follow-up call and tracked competitors
def _answer(content):
    return _Resp(200, _ok_payload(content=content))


FULL = ('{"company":{"primary_market":"India"},"executives":{"chairperson":{"name":"Chair C","source_urls":["https://x"]},'
        '"md_ceo":{"name":"Ceo O","source_urls":["https://x"]},"cfo":{"name":"Cfo P","source_urls":["https://x"]},'
        '"founders":[{"name":"Founder F","source_urls":["https://x"]}]},"competitors":[{"name":"DLF","context_term":"real estate","hq_country":"India","exchange_listed":true}]}')


def test_no_follow_up_when_every_required_slot_is_filled_and_no_tracked_competitor_is_missing():
    calls = []

    def post(url, headers=None, json=None, timeout=None):
        calls.append(json["messages"][0]["content"])
        return _answer(FULL)

    out = proposer.propose_multi("X", calls=2, post=post, api_key="k", tracked_competitors=["DLF Limited"])
    assert len(calls) == 2 and "follow_up" not in out
    assert proposer.missing_slots(out) == []


def test_one_small_follow_up_fills_only_the_empty_slots_and_never_a_third_pooled_call():
    calls = []
    partial = '{"company":{},"executives":{"chairperson":{"name":"Chair C","source_urls":["https://x"]}},"competitors":[]}'
    fill = '{"executives":{"cfo":{"name":"Cfo P","role":"CFO","source_urls":["https://n"]}},"competitors":[]}'

    def post(url, headers=None, json=None, timeout=None):
        prompt = json["messages"][0]["content"]
        calls.append(prompt)
        return _answer(fill if "small follow-up" in prompt else partial)

    out = proposer.propose_multi("X", calls=2, post=post, api_key="k")
    assert len(calls) == 3                                                     # two pooled + exactly one follow-up
    fu = calls[2]
    assert "ONLY these executive slots" in fu and "md_ceo, cfo, founder" in fu and "chairperson," not in fu.split("ONLY these executive slots")[1].split("\n")[0]
    assert "Describe these competitors" not in fu and "ownership claim" not in fu
    assert {e["name"]: e["slot"] for e in out["executives"]} == {"Chair C": "chairperson", "Cfo P": "cfo"}
    assert out["follow_up"]["slots"] == ["md_ceo", "cfo", "founder"] and out["calls"] == 3
    assert proposer.missing_slots(out) == ["md_ceo", "founder"]                # still empty: it is not asked a second time


def test_a_tracked_competitor_missing_from_the_pool_is_asked_about_in_the_follow_up_and_a_failed_follow_up_aborts():
    prompts = []
    fill = '{"executives":{},"competitors":[{"name":"Lodha Group","context_term":"real estate","hq_country":"India","source_urls":["https://l"]}]}'

    def post(url, headers=None, json=None, timeout=None):
        p = json["messages"][0]["content"]
        prompts.append(p)
        return _answer(fill if "small follow-up" in p else FULL)

    out = proposer.propose_multi("X", calls=2, post=post, api_key="k", tracked_competitors=["Lodha", "DLF Limited"])
    assert len(prompts) == 3 and "Lodha" in prompts[2] and "DLF Limited" not in prompts[2].split("already tracks")[1]     # DLF is already in the pool
    assert "Describe these competitors the company already tracks" in prompts[2] and "Fill ONLY these executive slots" not in prompts[2]
    assert {c["name"] for c in out["competitors"]} == {"DLF", "Lodha Group"}
    n = {"i": 0}

    def flaky(url, headers=None, json=None, timeout=None):
        n["i"] += 1
        return _answer(FULL) if n["i"] <= 2 else _Resp(500)

    with pytest.raises(SeedingAborted):
        proposer.propose_multi("X", calls=2, post=flaky, api_key="k", tracked_competitors=["Lodha"])


def test_tracked_competitors_go_through_the_same_guards_and_are_flagged(db):
    c, brand = _client(db)
    for n in ("Lodha", "Orris Infrastructure", "Godrej Capital"):
        db.add(Entity(id=uuid.uuid4(), client_id=c.id, name=n, entity_type="competitor"))
    db.commit()
    seen = {}

    def propose_fn(*a, **k):
        seen.update(k)
        return _proposal([], [
            {"name": "Lodha Group", "context_term": "real estate", "hq_country": "India", "aliases": ["Macrotech Developers"], "source_urls": []},
            {"name": "Orris Infrastructure", "context_term": "real estate", "hq_country": "India", "source_urls": []},
            {"name": "Godrej Capital", "context_term": "finance", "hq_country": "India", "source_urls": []},
        ], {"primary_market": "India"})

    plan = service.build_plan(db, c.id, propose_fn=propose_fn, fetch=_count_fetch({"Lodha Group": 9, "Orris Infrastructure": 1, "Godrej Capital": 50}), measure_aliases=False)
    assert sorted(seen["tracked_competitors"]) == ["Godrej Capital", "Lodha", "Orris Infrastructure"]
    by = {x["name"]: x for x in plan["competitors"]}
    assert by["Lodha Group"]["tracked"] and by["Lodha Group"]["selected"]                         # passes: shows in the result
    assert not by["Orris Infrastructure"]["validation"]["accepted"] and "sector count" in by["Orris Infrastructure"]["validation"]["reason"]
    assert "same group" in by["Godrej Capital"]["validation"]["reason"]                           # a tracked sister company is still not a peer


def test_competitor_news_count_uses_every_name_the_company_is_reported_under():
    assert validator.competitor_query("Lodha Group", "residential real estate", ["Macrotech Developers", "Lodha"]) == \
        '("Lodha Group" OR "Macrotech Developers") residential real estate'
    assert validator.competitor_query("DLF Limited", "real estate") == '"DLF" real estate'


def test_summary_lines_show_name_role_source_count_and_method_then_every_rejected_candidate(db):
    c, brand = _client(db)
    execs = [_cand("Chair C", "chairperson", ("https://www.godrejproperties.com/p",)), _cand("Nobody N", "management")]
    plan = service.build_plan(db, c.id, propose_fn=lambda *a, **k: _proposal(execs), fetch=_count_fetch({"Chair C": 5}), measure_aliases=False, fetch_text=_no_page)
    text = "\n".join(service.summary_lines(plan))
    assert "1. Chair C | chairperson | https://www.godrejproperties.com/p | news 20 | news count" in text
    assert "- Nobody N (management) | REJECTED: no Google News item" in text


def test_one_retry_asks_for_readable_pages_for_unverified_one_or_two_item_executives_and_revalidates_them(db):
    c, brand = _client(db)
    cdn = "https://gplwebsitecdnblob.blob.core.windows.net/x/ar.pdf"
    nse = "https://www.bseindia.com/xml-data/corpfiling/transcript.html"
    execs = [{"name": "Rajendra Khetawat", "slot": "cfo", "role": "Chief Financial Officer", "source_urls": [cdn]}, _cand("Chair C", "chairperson")]
    calls = []

    def retry(company, people):
        calls.append(people)
        return {"executives": [{"name": "Rajendra Khetawat", "slot": "retry", "source_urls": [nse]}], "cost_usd": 0.01}

    khet = iter([1, 1, 0, 0] * 2)                                       # 2 news items on each of the two validations

    def fetch(q, a, b):
        return [object()] * next(khet, 0) if '"Rajendra Khetawat"' in q else ([object()] * 5 if '"Chair C"' in q else [])

    pages = {nse: "Earnings call: Mr. Rajendra Khetawat, CFO of the company, said"}
    plan = service.build_plan(db, c.id, propose_fn=lambda *a, **k: _proposal(execs), fetch=fetch, measure_aliases=False,
                              fetch_text=lambda u: pages.get(u), retry_fn=retry)
    assert calls == [[{"name": "Rajendra Khetawat", "role": "Chief Financial Officer"}]]            # asked once, only for the unverified person
    k = {x["name"]: x for x in plan["executives"]}["Rajendra Khetawat"]
    assert k["selected"] and k["validation"]["method"] == "exchange filing" and k["validation"]["verified_page"] == nse and k["validation"]["retried"]
    assert plan["retry"]["asked"] == ["Rajendra Khetawat"] and plan["cost_usd"] == pytest.approx(0.024)
    calls.clear()
    service.build_plan(db, c.id, propose_fn=lambda *a, **k: _proposal([_cand("Chair C", "chairperson")]), fetch=_count_fetch({"Chair C": 5}),
                       measure_aliases=False, fetch_text=_no_page, retry_fn=retry)
    assert calls == []                                                                               # nothing to retry, no call


def test_follow_up_asks_for_a_page_per_ownership_claim_and_the_listing_of_every_pooled_competitor():
    prompts = []
    pooled = ('{"company":{"primary_market":"India"},"executives":{"chairperson":{"name":"A","source_urls":["https://x"]},"md_ceo":{"name":"B","source_urls":["https://x"]},'
              '"cfo":{"name":"C","source_urls":["https://x"]},"founders":[{"name":"D","source_urls":["https://x"]}]},'
              '"competitors":[{"name":"MakeMyTrip","context_term":"online travel","hq_country":"India"},'
              '{"name":"Goibibo","context_term":"online travel","hq_country":"India","parent_company":"MakeMyTrip"}]}')
    fill = ('{"ownership_evidence":[{"candidate":"Goibibo","child":"Goibibo","parent":"MakeMyTrip","still_owned":true,"source_urls":["https://wiki/Goibibo"]}],'
            '"listing":[{"name":"MakeMyTrip","exchange_listed":true,"ticker":"MMYT"},{"name":"Goibibo","exchange_listed":false}]}')

    def post(url, headers=None, json=None, timeout=None):
        p = json["messages"][0]["content"]
        prompts.append(p)
        return _answer(fill if "small follow-up" in p else pooled)

    out = proposer.propose_multi("EaseMyTrip", calls=2, post=post, api_key="k")
    assert len(prompts) == 3 and "Goibibo is owned by MakeMyTrip" in prompts[2] and "CURRENTLY listed on NSE or BSE" in prompts[2]
    assert "MakeMyTrip; Goibibo" in prompts[2] and "Fill ONLY these executive slots" not in prompts[2]
    by = {c["name"]: c for c in out["competitors"]}
    assert by["MakeMyTrip"]["exchange_listed"] is True and by["Goibibo"]["exchange_listed"] is False
    assert out["ownership_evidence"][0]["source_urls"] == ["https://wiki/Goibibo"] and out["follow_up"]["ownership_claims"] == 1


def test_ownership_evidence_is_matched_to_the_right_competitor_even_when_the_model_puts_the_sentence_in_candidate():
    names = ["MakeMyTrip Limited", "Goibibo", "ixigo"]
    ek = service._evidence_key
    assert ek({"candidate": "Goibibo is owned by MakeMyTrip Limited", "child": "Goibibo"}, names) == "goibibo"
    assert ek({"candidate": "ixigo is owned by MakeMyTrip Limited", "child": ""}, names) == "ixigo"          # earliest name in the sentence = the child
    assert ek({"candidate": "ixigo", "child": "ixigo"}, names) == "ixigo"


# ------------------------------------------------------------------------------------------ add aliases to a seeded entity
def _yatra_setup(db):
    c, brand = _client(db, name="EaseMyTrip", domain="easemytrip.com")
    yat = Entity(id=uuid.uuid4(), client_id=c.id, name="Yatra.com", entity_type="competitor")
    db.add(yat)
    db.add(EntityKeyword(entity_id=yat.id, keyword_text="Yatra.com", match_type="exact", category="PRIMARY", priority=1, is_active=True))
    db.add(SeededEntity(client_id=c.id, entity_id=yat.id, kind="competitor", name="Yatra.com", rank=2, context_term="online travel",
                        status="active", validated=True, aliases=[]))
    docs = {}
    for key, title, body in [("a", "Yatra Online, Inc. announces results", "online travel"), ("b", "Yatra.com offers", "x"),
                             ("c", "Bharat Jodo Yatra reaches Delhi", "x")]:
        d = Document(id=uuid.uuid4(), url=f"http://y.test/{key}", title=title, normalized_content=body, published_at=dt.datetime.now(dt.timezone.utc))
        db.add(d)
        db.flush()
        docs[key] = d
        db.add(EntityMention(document_id=d.id, entity_id=brand.id, mention_count=1))        # visible to the client's pages
    db.commit()
    return c, yat, docs


def test_add_aliases_reports_only_without_write_and_applies_the_alias_safety_rule(db):
    c, yat, docs = _yatra_setup(db)
    noisy = _news(*(["Yatra Online results"] * 14 + ["Bharat Jodo Yatra rally"] * 36))                # the bare word is mostly the Hindi word
    out = service.add_aliases(db, c.id, "yatra.com", ["Yatra Online", "Yatra"], write=False, fetch=lambda q, a, b: noisy)
    by = {a["alias"]: a for a in out["resolved"]}
    assert by["Yatra Online"]["enabled"] and not by["Yatra"]["enabled"] and "false-match" in by["Yatra"]["reason"]
    assert out["enabled"] == ["Yatra Online"] and out["written"] is False
    assert db.query(EntityKeyword).filter(EntityKeyword.entity_id == yat.id).count() == 1                # nothing written
    assert db.query(SeededEntity).filter(SeededEntity.entity_id == yat.id).one().aliases == []


def test_add_aliases_with_write_stores_them_adds_keywords_and_rematches_visible_documents(db):
    c, yat, docs = _yatra_setup(db)
    noisy = _news(*(["Yatra Online results"] * 14 + ["Bharat Jodo Yatra rally"] * 36))
    out = service.add_aliases(db, c.id, "Yatra.com", ["Yatra Online", "Yatra"], write=True, fetch=lambda q, a, b: noisy)
    assert out["written"] is True and out["rematch"]["Yatra.com"]["new_mentions"] == 2                   # b (the name) and a (the alias); c is the Hindi word
    row = db.query(SeededEntity).filter(SeededEntity.entity_id == yat.id).one()
    assert {(a["alias"], a["enabled"]) for a in row.aliases} == {("Yatra Online", True), ("Yatra", False)}
    kws = {k.keyword_text for k in db.query(EntityKeyword).filter(EntityKeyword.entity_id == yat.id)}
    assert kws == {"Yatra.com", "Yatra Online"}                                                          # the disabled bare alias is not a keyword
    assert {m.document_id for m in db.query(EntityMention).filter(EntityMention.entity_id == yat.id)} == {docs["a"].id, docs["b"].id}
    again = service.add_aliases(db, c.id, "Yatra.com", ["Yatra Online"], write=True, fetch=lambda q, a, b: noisy)
    assert again["new"] == [] and again["written"] is False                                              # re-running adds nothing
    assert db.query(EntityKeyword).filter(EntityKeyword.entity_id == yat.id, EntityKeyword.keyword_text == "Yatra Online").count() == 1


def test_add_aliases_for_an_unknown_or_retired_entity_changes_nothing(db):
    c, yat, docs = _yatra_setup(db)
    assert "error" in service.add_aliases(db, c.id, "Nobody", ["Nobody Ltd"], write=True)
    db.query(SeededEntity).filter(SeededEntity.entity_id == yat.id).update({"status": "retired"})
    db.commit()
    assert "error" in service.add_aliases(db, c.id, "Yatra.com", ["Yatra Online"], write=True)


# ----------------------------------------------------------------------- search-hit attribution (document_feed_hits)
def _count_hits_on(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "SEEDED_COUNT_SEARCH_HITS", True)


def _attr_setup(db):
    from app.models.document_feed_hit import DocumentFeedHit  # noqa: F401
    c, brand = _client(db)
    gp = Entity(id=uuid.uuid4(), client_id=c.id, name="Gaurav Pandey", entity_type="person")
    other = Entity(id=uuid.uuid4(), client_id=c.id, name="Not Seeded", entity_type="person")
    db.add_all([gp, other])
    db.add(SeededEntity(client_id=c.id, entity_id=gp.id, kind="executive", name="Gaurav Pandey", rank=2, status="active", validated=True))
    now = dt.datetime.now(dt.timezone.utc)
    docs = {}
    for key, title, body in [
        ("named", "Gaurav Pandey, Godrej Properties CEO, on demand", "x"),                  # already counted: full name + company in the text
        ("company", "Godrej Properties buys land in Kolkata", "residential project"),         # body-only mention: company in the text
        ("role", "Housing major's CEO sees strong demand", "x"),                              # role word only
        ("surname", "Pandey says launches on track", "x"),                                    # surname only
        ("unrelated", "Cricket team wins the series", "sports desk"),                         # the search returned it, nothing in the text fits
        ("nohit", "Godrej Properties launches a tower", "x"),                                  # never returned by the executive's search
    ]:
        d = Document(id=uuid.uuid4(), url=f"http://a.test/{key}", content_hash=f"h-{key}", title=title, normalized_content=body, published_at=now)
        db.add(d)
        db.flush()
        docs[key] = d
        db.add(EntityMention(document_id=d.id, entity_id=brand.id, mention_count=1))
    db.add(EntityMention(document_id=docs["named"].id, entity_id=gp.id, mention_count=1))
    db.commit()
    return c, gp, other, docs


def test_a_search_hit_is_recorded_for_a_held_document_by_url_or_by_headline_hash_and_never_twice(db):
    from app.models.document_feed_hit import DocumentFeedHit
    from app.services.seeding import attribution
    from app.utils.text_processing import generate_content_hash
    c, gp, other, docs = _attr_setup(db)
    docs["company"].content_hash = generate_content_hash("Godrej Properties buys land in Kolkata")
    db.commit()
    assert attribution.record_hit_for_item(db, c.id, gp.id, {"url": "http://a.test/company?utm=1", "content": "x"}, "google_news", "q")       # by canonical URL
    assert attribution.record_hit_for_item(db, c.id, gp.id, {"url": "http://elsewhere.test/other-url", "content": "Godrej Properties buys land in Kolkata"}, "google_news", "q")   # same headline, another URL
    assert not attribution.record_hit_for_item(db, c.id, gp.id, {"url": "http://nowhere.test/x", "content": "never saved"}, "google_news", "q")
    assert db.query(DocumentFeedHit).filter(DocumentFeedHit.entity_id == gp.id).count() == 1          # both resolved to the one held document
    attribution.record_hit(db, c.id, gp.id, docs["company"].id, "google_news", "q")
    assert db.query(DocumentFeedHit).count() == 1


def test_attribute_hits_adds_a_mention_only_when_the_stored_text_holds_the_company_the_surname_or_a_role(db, monkeypatch):
    _count_hits_on(monkeypatch)
    from app.services.seeding import attribution
    c, gp, other, docs = _attr_setup(db)
    for key in ("named", "company", "role", "surname", "unrelated"):
        attribution.record_hit(db, c.id, gp.id, docs[key].id, "google_news", "q")
    preview = attribution.attribute_hits(db, c.id, write=False)
    assert preview["Gaurav Pandey"] == {"hits": 5, "already_mentioned": 1, "attributed": 3, "blocked_by_guard": 1}
    assert db.query(EntityMention).filter(EntityMention.entity_id == gp.id).count() == 1                  # report only
    out = attribution.attribute_hits(db, c.id)
    assert out["Gaurav Pandey"]["attributed"] == 3
    got = {m.document_id for m in db.query(EntityMention).filter(EntityMention.entity_id == gp.id)}
    assert got == {docs["named"].id, docs["company"].id, docs["role"].id, docs["surname"].id}              # the unrelated document is not attributed
    assert db.query(EntityMention).filter(EntityMention.entity_id == gp.id, EntityMention.document_id == docs["company"].id).one().confidence_score == 0.6
    assert attribution.attribute_hits(db, c.id)["Gaurav Pandey"]["attributed"] == 0                         # idempotent
    assert db.query(EntityMention).filter(EntityMention.entity_id == other.id).count() == 0


def test_the_executive_gate_counts_hit_documents_that_pass_the_guard_and_changes_nothing_without_hits(db, monkeypatch):
    _count_hits_on(monkeypatch)
    from app.services.seeding import attribution, gates
    c, gp, other, docs = _attr_setup(db)
    # a body-only document with a mention but no hit is NOT counted (the text has neither the full name with the company)
    db.add(EntityMention(document_id=docs["nohit"].id, entity_id=gp.id, mention_count=1))
    db.commit()
    before = gates.seeded_gate_doc_ids(db, c.id, [gp.id])[gp.id]
    assert before == {docs["named"].id}
    for key in ("company", "role", "unrelated"):
        attribution.record_hit(db, c.id, gp.id, docs[key].id, "google_news", "q")
    attribution.attribute_hits(db, c.id)
    after = gates.seeded_gate_doc_ids(db, c.id, [gp.id])[gp.id]
    assert after == {docs["named"].id, docs["company"].id, docs["role"].id}                                 # hit + mention + guard; "unrelated" has a hit but fails the guard; "nohit" has no hit
    assert gates.guard_passes("x", "y", ["godrej properties"], "Gaurav Pandey") is False
    assert gates.guard_passes("Pandey said", "", ["godrej properties"], "Gaurav Pandey") is True


def test_backfill_records_the_hits_of_a_seeded_executives_slice_and_attributes_them(db, monkeypatch):
    _count_hits_on(monkeypatch)
    from app.models.document_feed_hit import DocumentFeedHit
    from app.services.backfill import engine as bf
    c, gp, other, docs = _attr_setup(db)

    class FakeAdapter:
        def normalize(self, raw, source_id):
            return {"url": raw["url"], "content": raw.get("content", "")}

    monkeypatch.setattr(bf, "load_adapter", lambda src: FakeAdapter())
    fetched = [{"url": "http://a.test/company"}, {"url": "http://a.test/role"}, {"url": "http://not-held.test/z"}]

    def fetch(query, s, e, ctx):
        return fetched if "Gaurav" in query and "fraud" not in query else []

    def ingest(db_, client_id, src, raw, **kw):
        return {"saved": 0, "deduped": len(raw), "skipped_undated": 0, "dropped_irrelevant": 0}

    cfg = bf.BackfillConfig(sources=("google_news",), max_slices_per_run=200, relevance_filter=False)
    summary = bf.run_client(db, c.id, cfg, fetchers={"google_news": fetch}, ingest=ingest)
    assert {h.document_id for h in db.query(DocumentFeedHit).filter(DocumentFeedHit.entity_id == gp.id)} == {docs["company"].id, docs["role"].id}
    assert summary["attributed"]["Gaurav Pandey"] == 2
    assert {m.document_id for m in db.query(EntityMention).filter(EntityMention.entity_id == gp.id)} == {docs["named"].id, docs["company"].id, docs["role"].id}


def test_run_pipeline_links_the_documents_a_seeded_executives_feed_returns_even_when_already_held(db, monkeypatch):
    _count_hits_on(monkeypatch)
    import app.workers.aggregation_tasks as agg
    import app.adapters.registry as registry
    import app.services.document_service as docsvc
    import app.workers.collection_tasks as ct
    from app.models.document_feed_hit import DocumentFeedHit
    from app.services.client_service import provision_entity_search_feeds

    c, brand = _client(db)
    gp = Entity(id=uuid.uuid4(), client_id=c.id, name="Gaurav Pandey", entity_type="person")
    dlf = Entity(id=uuid.uuid4(), client_id=c.id, name="DLF", entity_type="competitor")
    db.add_all([gp, dlf])
    db.add_all([SeededEntity(client_id=c.id, entity_id=gp.id, kind="executive", name="Gaurav Pandey", rank=2, status="active", validated=True),
                SeededEntity(client_id=c.id, entity_id=dlf.id, kind="competitor", name="DLF", rank=1, context_term="real estate", status="active", validated=True)])
    db.commit()
    exec_feeds = provision_entity_search_feeds(db, c.id, "Gaurav Pandey", co_occur_with="Godrej Properties", quote=True, co_quoted=True)
    provision_entity_search_feeds(db, c.id, "DLF", co_occur_with="real estate", quote=True, co_quoted=False)
    plain_feed = RSSFeed(feed_name="Brand Google News Feed", feed_url="https://news.google.com/rss/search?q=Godrej", client_id=c.id, is_active=True,
                         source_type="entity_search", source_format="rss")
    db.add(plain_feed)
    held = {}
    for i in range(3):
        d = Document(id=uuid.uuid4(), url=f"http://held.test/art-{i}", content_hash=f"hh{i}", title="Godrej Properties news %d" % i, normalized_content="x",
                     published_at=dt.datetime.now(dt.timezone.utc))
        db.add(d)
        held[i] = d
    db.commit()

    class FakeAdapter:
        def fetch(self, url):
            return [{"link": f"http://held.test/art-{i}"} for i in range(3)] + [{"link": "http://new.test/not-held"}]

        def normalize(self, entry, source_id):
            return {"url": entry["link"], "title": "t", "content": "c", "published_at": dt.datetime.now(dt.timezone.utc), "source_id": source_id}

    monkeypatch.setitem(registry.ADAPTER_REGISTRY, "rss", FakeAdapter)
    monkeypatch.setitem(registry.ADAPTER_REGISTRY, "gdelt_json", FakeAdapter)
    monkeypatch.setitem(registry.ADAPTER_REGISTRY, "hn_algolia_json", FakeAdapter)
    monkeypatch.setattr(docsvc, "process_and_save_document", lambda db_, nd: (False, True, 0))       # every item is already held (deduped)
    monkeypatch.setattr(ct, "_get_or_create_source", lambda db_, feed: SimpleNamespace(id=uuid.uuid4()))
    for name in ("_stage_collect_youtube", "_stage_collect_instagram", "_stage_collect_reddit"):
        monkeypatch.setattr(agg, name, lambda *a, **k: [])
    monkeypatch.setattr(agg, "_stale_pending_search_doc_ids", lambda *a, **k: [])
    from app.schemas import document as docschema
    monkeypatch.setattr(docschema, "NormalizedDocument", lambda **kw: SimpleNamespace(**kw))

    agg._stage_collect(SimpleNamespace(client_id=c.id, run_id="r1", worker_id="w1"), db)
    hits = db.query(DocumentFeedHit).all()
    assert {h.entity_id for h in hits} == {gp.id}                                      # only the executive's feeds link; the brand and competitor feeds do not
    assert {h.document_id for h in hits} == {held[0].id, held[1].id, held[2].id}      # the held ones, once each; the unheld item has nothing to link
    assert {h.query for h in hits} <= {f.feed_url for f in exec_feeds}
    # the guard: these held documents name Godrej Properties in the title, so they are attributed to the executive
    assert {m.document_id for m in db.query(EntityMention).filter(EntityMention.entity_id == gp.id)} == {held[0].id, held[1].id, held[2].id}


def test_with_the_switch_off_hits_are_recorded_but_nothing_is_attributed_or_counted(db):
    from app.core.config import settings
    from app.models.document_feed_hit import DocumentFeedHit
    from app.services.seeding import attribution, gates
    assert settings.SEEDED_COUNT_SEARCH_HITS is False                                    # the shipped default
    c, gp, other, docs = _attr_setup(db)
    db.add(EntityMention(document_id=docs["company"].id, entity_id=gp.id, mention_count=1))   # a mention exists, but the text does not hold name + company
    db.commit()
    attribution.record_hit(db, c.id, gp.id, docs["company"].id, "google_news", "q")
    attribution.record_hit(db, c.id, gp.id, docs["role"].id, "google_news", "q")
    assert db.query(DocumentFeedHit).count() == 2                                         # recorded
    out = attribution.attribute_hits(db, c.id)                                            # report only: shows what turning it on would add
    assert out["Gaurav Pandey"]["attributed"] == 1 and db.query(EntityMention).filter(EntityMention.entity_id == gp.id).count() == 2
    assert gates.seeded_gate_doc_ids(db, c.id, [gp.id])[gp.id] == {docs["named"].id}      # the gate is exactly as before
