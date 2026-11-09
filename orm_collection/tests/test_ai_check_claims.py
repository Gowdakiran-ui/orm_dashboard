"""AI claim cross-check: triage of the sentences in an AI-check run (stored with the run) and the match against XOOP incidents.
In-memory SQLite and a fake model call only: nothing here reaches OpenRouter or a real database."""
import datetime
import os
import sys
import uuid
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
from app.models.document import Document
from app.models.entity import Entity
from app.models.risk import RiskEvent
from app.models.ai_check import AiCheckRun, AiCheckAnswer, AiCheckFlag
import app.api.endpoints.client_intelligence as ci
from app.services.ai_check import claims, service as svc, triage as tr


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
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setenv("AI_CHECK_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")


ADMIN = SimpleNamespace(role="super_admin")
VIEWER = SimpleNamespace(role="client_user")


def _client(db, name="EaseMyTrip"):
    c = Client(id=uuid.uuid4(), name=name)
    db.add(c)
    db.commit()
    return c


# ---- candidate sentences ------------------------------------------------------------------------------------------------------
def ans(prompt, rep, text, cited=("a.com",)):
    return {"prompt_key": prompt, "repeat_index": rep, "text": text, "cited_domains": list(cited)}


def test_candidates_are_distinct_sentences_with_an_accusation_word_and_remember_where_they_appeared():
    s = "The ED filed a chargesheet against the founder of the company."
    out = tr.candidate_sentences([
        ans("legal_controversies", 0, f"## Heading\n\n{s} The company is based in Delhi and sells flights."),
        ans("legal_controversies", 1, s),
        ans("main_case", 2, f"- {s}"),
    ])
    assert len(out) == 1 and out[0]["sentence"] == s
    assert out[0]["occurrences"] == [{"prompt": "legal_controversies", "repeats": [1, 2]}, {"prompt": "main_case", "repeats": [3]}]


def test_short_fragments_and_sentences_without_an_accusation_word_are_skipped():
    out = tr.candidate_sentences([ans("p", 0, "Fraud case\nThe company sells flights and hotels across India.\nIt was founded in 2008 by two brothers.")])
    assert out == []


def test_inline_domains_come_from_markdown_links_and_from_domains_named_in_the_text():
    out = tr.candidate_sentences([
        ans("p", 0, "[livelaw.in](https://www.livelaw.in/x) reports the commission fined the company over the refund dispute.", cited=("livelaw.in", "b.com")),
        ans("p", 1, "inventiva.co.in says a fraud case was registered against the company in Chandigarh.", cited=("inventiva.co.in",)),
        ans("p", 2, "The company faced a fraud case in Chandigarh court and denied everything.", cited=("zzz.com",)),
    ])
    by = {o["sentence"][:12]: o for o in out}
    assert by["livelaw.in <"]["inline_domains"] == ["livelaw.in"] and by["livelaw.in <"]["cited_domains"] == ["b.com", "livelaw.in"]
    assert by["inventiva.co"]["inline_domains"] == ["inventiva.co.in"]
    assert by["The company "]["inline_domains"] == []


# ---- the model's answer ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ('```json\n{"accusation": true, "about": "client", "framing": "FACT", "event": "ed chargesheet pitti mahadev"}\n```', (True, "client", "FACT", "ed chargesheet pitti mahadev")),
    ('{"accusation": false, "about": "other", "framing": "HEDGED"}', (False, "other", "HEDGED", None)),
    ('{"accusation":true,"about":"Executive","framing":"attributed","event":"CBI FIR"}', (True, "executive", "ATTRIBUTED", "cbi fir")),
])
def test_triage_answer_is_read_with_regexes(text, expected):
    r = tr.parse_triage(text)
    assert (r["accusation"], r["about"], r["framing"], r["event"]) == expected


@pytest.mark.parametrize("text", [None, "", "no idea", '{"accusation": true, "about": "client"}', '{"about": "client", "framing": "FACT"}'])
def test_unreadable_triage_answer_is_none(text):
    assert tr.parse_triage(text) is None


class _Resp:
    def __init__(self, content, status=200, cost=0.0006):
        self.status_code, self._c, self._cost = status, content, cost

    def json(self):
        return {"choices": [{"message": {"content": self._c}}], "usage": {"cost": self._cost}}


FACT = '{"accusation": true, "about": "client", "framing": "FACT", "event": "ed chargesheet pitti mahadev betting"}'
HEDGED = '{"accusation": true, "about": "client", "framing": "HEDGED", "event": "x y z"}'


def test_triage_call_sends_one_sentence_at_temperature_zero_and_fails_safe():
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        return _Resp(FACT)

    v = tr.triage_sentence("The ED filed a chargesheet against the founder.", "EaseMyTrip", ["Nishant Pitti"], "k", post=post)
    assert v["framing"] == "FACT" and v["cost_usd"] == 0.0006 and tr.is_flagged(v)
    assert seen["body"]["temperature"] == 0 and seen["body"]["model"] == "anthropic/claude-haiku-4.5" and "plugins" not in seen["body"]
    assert "Nishant Pitti" in seen["body"]["messages"][1]["content"]
    assert tr.triage_sentence("s", "C", [], None, post=post) is None
    assert tr.triage_sentence("s", "C", [], "k", post=lambda *a, **k: _Resp("x", status=500)) is None
    assert tr.triage_sentence("s", "C", [], "k", post=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))) is None


def test_flagged_means_accusation_about_the_client_or_an_executive_stated_as_fact():
    v = lambda a, w, f: {"accusation": a, "about": w, "framing": f}
    assert tr.is_flagged(v(True, "client", "FACT")) and tr.is_flagged(v(True, "executive", "FACT"))
    assert not tr.is_flagged(v(True, "other", "FACT"))
    assert not tr.is_flagged(v(False, "client", "FACT"))
    assert not tr.is_flagged(v(True, "client", "HEDGED")) and not tr.is_flagged(v(True, "client", "ATTRIBUTED"))


# ---- stored with the run -----------------------------------------------------------------------------------------------------------
def test_triage_run_stores_one_row_per_sentence_adds_its_cost_and_counts_flagged(db):
    c = _client(db)
    run = svc.start_run(db, c.id)
    answers = [ans("legal_controversies", 0, "The ED filed a chargesheet against the founder of the company. Reuters reports an alleged fraud case in Delhi court.")]
    replies = iter([_Resp(FACT), _Resp(HEDGED, cost=0.0007)])
    n = tr.triage_run(db, run, "EaseMyTrip", ["Nishant Pitti"], answers, "k", post=lambda *a, **k: next(replies))
    rows = db.query(AiCheckFlag).filter(AiCheckFlag.run_id == run.id).order_by(AiCheckFlag.flagged.desc()).all()
    assert n == 1 and len(rows) == 2
    assert rows[0].flagged is True and rows[0].framing == "FACT" and rows[0].event == "ed chargesheet pitti mahadev betting"
    assert rows[0].occurrences == [{"prompt": "legal_controversies", "repeats": [1]}] and rows[1].flagged is False
    assert run.cost_usd == pytest.approx(0.0013)


def test_a_failed_triage_call_stores_nothing_for_that_sentence_and_the_cap_stops_triage(db):
    c = _client(db)
    run = svc.start_run(db, c.id)
    text = " ".join(f"The company faced fraud case number {i} in a Delhi court today." for i in range(10))
    assert tr.triage_run(db, run, "C", [], [ans("p", 0, text)], "k", post=lambda *a, **k: _Resp("nonsense")) == 0
    assert db.query(AiCheckFlag).count() == 0
    run.cost_usd = 0.5995
    calls = []
    tr.triage_run(db, run, "C", [], [ans("p", 0, text)], "k", post=lambda *a, **k: calls.append(1) or _Resp(FACT), cap_usd=0.60)
    assert calls == []                                                                    # no budget left: no call


def _web_or_triage(web_text):
    """A fake post for a whole run: web calls (have a 'plugins' key) get an answer; triage calls get a verdict."""
    def post(url, headers=None, json=None, timeout=None):
        if "plugins" in json:
            r = _Resp(web_text, cost=0.0125)
            r._payload_urls = ["https://www.livelaw.in/x"]
            return type("R", (), {"status_code": 200, "json": lambda self: {"choices": [{"message": {"content": web_text, "annotations": [{"url_citation": {"url": "https://www.livelaw.in/x", "title": "T"}}]}}], "usage": {"cost": 0.0125}}})()
        return _Resp(FACT)
    return post


def test_a_full_run_triages_its_answers_and_the_run_cost_includes_the_triage(db):
    c = _client(db)
    prompts = [{"key": "legal_controversies", "label": "L", "text": "Q?"}]
    run = svc.start_run(db, c.id, 1)
    svc.execute_run(db, run, prompts, "k", post=_web_or_triage("The ED filed a chargesheet against the founder of the company."), client_name="EaseMyTrip", executives=["Nishant Pitti"])
    assert (run.status, run.calls_ok) == ("completed", 3)
    flags = db.query(AiCheckFlag).filter(AiCheckFlag.run_id == run.id).all()
    assert len(flags) == 1 and flags[0].flagged and flags[0].occurrences == [{"prompt": "legal_controversies", "repeats": [1, 2, 3]}]
    assert run.cost_usd == pytest.approx(3 * 0.0125 + 0.0006)


def test_triage_never_changes_a_run_that_stopped_at_the_cap_and_never_breaks_a_run(db, monkeypatch):
    c = _client(db)
    prompts = [{"key": "legal_controversies", "label": "L", "text": "Q?"}]
    run = svc.start_run(db, c.id, 1)
    svc.execute_run(db, run, prompts, "k", post=_web_or_triage("The ED filed a chargesheet against the founder of the company."), cap_usd=0.03)
    assert run.status == "stopped_at_cap" and db.query(AiCheckFlag).count() == 0
    monkeypatch.setattr(tr, "triage_run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    run2 = svc.start_run(db, c.id, 1)
    svc.execute_run(db, run2, prompts, "k", post=_web_or_triage("The ED filed a chargesheet against the founder."))
    assert run2.status == "completed" and run2.calls_ok == 3                              # the answers are safe


# ---- XOOP side ---------------------------------------------------------------------------------------------------------------------
def _risk_doc(db, c, title, score, days_ago, status=None, event=None, etype="brand"):
    ent = db.query(Entity).filter(Entity.client_id == c.id, Entity.entity_type == etype).first()
    if ent is None:
        ent = Entity(id=uuid.uuid4(), client_id=c.id, name=c.name, entity_type=etype)
        db.add(ent)
        db.commit()
    d = Document(id=uuid.uuid4(), url=f"http://t/{uuid.uuid4()}", normalized_content="x", title=title,
                 published_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago))
    db.add(d)
    db.commit()
    expl = {"case_status": status, "case_event": event} if status else {}
    db.add(RiskEvent(client_id=c.id, document_id=d.id, entity_id=ent.id, risk_score=score, risk_level="X", explainability=expl))
    db.commit()
    return d.id


def test_xoop_incidents_group_documents_and_carry_the_leads_status(db):
    c = _client(db)
    for t in ("ED chargesheets EaseMyTrip promoter Nishant Pitti in Mahadev betting app case - ThePrint",
              "ED Chargesheets EaseMyTrip Cofounder Nishant Pitti In Mahadev Betting Case - Inc42"):
        _risk_doc(db, c, t, 51.0, 30, "charged", "ed chargesheet nishant pitti mahadev betting")
    _risk_doc(db, c, "Quiet news - Mint", 10.0, 3)                                                   # LOW: not an incident
    _risk_doc(db, c, "Rival raided - X", 90.0, 3, "probe", "rival raided", etype="competitor")          # a competitor's: not this client's
    incs = claims.xoop_incidents(db, c)
    assert len(incs) == 1 and incs[0]["status"] == "charged" and incs[0]["documents"] == 2 and incs[0]["sources"] == 2


def test_match_needs_two_shared_words_and_prefers_the_larger_incident_on_a_tie():
    inc = lambda toks, docs, st: {"tokens": frozenset(toks), "documents": docs, "status": st, "title": "T", "sources": docs}
    a, b = inc({"ed", "raid", "pitti", "mahadev"}, 10, "probe"), inc({"ed", "chargesheet", "pitti", "mahadev"}, 9, "charged")
    assert claims.match_incident(frozenset({"ed", "chargesheet", "pitti"}), [a, b]) is b            # 3 shared beats 2
    assert claims.match_incident(frozenset({"ed", "pitti"}), [a, b]) is a                            # tie: more documents
    assert claims.match_incident(frozenset({"ed"}), [a, b]) is None                                  # one shared word is not enough
    assert claims.match_incident(frozenset({"zzz"}), []) is None


def test_note_says_when_the_ai_states_as_fact_something_xoop_labels_allegation_probe_or_charged():
    m = lambda st: {"status": st}
    assert claims.claim_note("FACT", None) == "Not matched automatically."
    assert claims.claim_note("FACT", m("probe")) == "The AI states this as fact; XOOP labels the matching story a probe."
    assert claims.claim_note("FACT", m("charged")) == "The AI states this as fact; XOOP labels the matching story charged."
    assert claims.claim_note("FACT", m("allegation")) == "The AI states this as fact; XOOP labels the matching story an allegation."
    assert claims.claim_note("FACT", m("penalty_or_order")) == "Matches an XOOP incident labelled penalty or order."
    assert claims.claim_note("FACT", m("settled")) == "Matches an XOOP incident labelled settled."
    assert claims.claim_note("FACT", m(None)) == "Matching XOOP incident has no case status yet."


def _flag(db, run, sentence, event, flagged=True, framing="FACT", occ=None):
    db.add(AiCheckFlag(id=uuid.uuid4(), run_id=run.id, client_id=run.client_id, sentence=sentence, occurrences=occ or [{"prompt": "legal_controversies", "repeats": [1, 2]}],
                       accusation=True, about="executive", framing=framing, flagged=flagged, event=event, inline_domains=[], cited_domains=["livelaw.in"]))
    db.commit()


def test_report_gives_super_admins_the_claim_checks_and_nobody_else(db):
    c = _client(db)
    for t in ("ED chargesheets EaseMyTrip promoter Nishant Pitti in Mahadev betting app case - ThePrint",
              "ED Chargesheets EaseMyTrip Cofounder Nishant Pitti In Mahadev Betting Case - Inc42"):
        _risk_doc(db, c, t, 51.0, 30, "charged", "ed chargesheet nishant pitti mahadev betting")
    run = svc.start_run(db, c.id)
    db.add(AiCheckAnswer(id=uuid.uuid4(), run_id=run.id, client_id=c.id, prompt_key="legal_controversies", prompt_text="Q", repeat_index=0, answer_text="a", cited_urls=[], cited_domains=[]))
    db.commit()
    _flag(db, run, "The ED has filed a chargesheet against Nishant Pitti in the Mahadev case.", "ed chargesheet nishant pitti mahadev")
    _flag(db, run, "The company was fined for a billing fraud in Mumbai last year.", "easemytrip billing fraud mumbai")
    _flag(db, run, "Reuters reports an alleged fraud.", "x", flagged=False, framing="ATTRIBUTED")
    out = svc.latest_report(db, c, is_admin=True)["claim_checks"]
    assert len(out) == 2                                                                              # only flagged sentences
    hit = next(o for o in out if "chargesheet" in o["sentence"])
    assert hit["matched"]["status"] == "charged" and hit["matched"]["documents"] == 2
    assert hit["note"] == "The AI states this as fact; XOOP labels the matching story charged."
    assert hit["questions"] == ["Legal cases and controversies"] and hit["repeats"] == [1, 2]
    miss = next(o for o in out if "billing" in o["sentence"])
    assert miss["matched"] is None and miss["note"] == "Not matched automatically."
    assert svc.latest_report(db, c, is_admin=False)["claim_checks"] == []


def test_endpoint_returns_claim_checks_to_super_admins_only(db):
    c = _client(db)
    run = svc.start_run(db, c.id)
    db.add(AiCheckAnswer(id=uuid.uuid4(), run_id=run.id, client_id=c.id, prompt_key="trustworthy", prompt_text="Q", repeat_index=0, answer_text="a", cited_urls=[], cited_domains=[]))
    db.commit()
    _flag(db, run, "A fraud case was registered against the founder of the company.", "fraud case founder")
    assert len(ci.get_client_ai_check(c.id, db, ADMIN)["claim_checks"]) == 1
    assert ci.get_client_ai_check(c.id, db, VIEWER)["claim_checks"] == []


def test_estimate_now_lists_the_triage_calls_and_cost():
    e = svc.estimate()
    assert e["calls"] == 24 and e["triage_calls"] == 70 and e["triage_cost_usd"] == pytest.approx(0.049)
    assert e["total_estimate_usd"] == pytest.approx(e["estimated_cost_usd"] + e["triage_cost_usd"])
