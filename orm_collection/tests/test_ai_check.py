"""'What AI says about you' check: prompts, source reliability, the web call, a run, and the read-back.

In-memory SQLite and a fake web call only: nothing here reaches OpenRouter or a real database (DATABASE_URL is forced to an
unreachable dummy)."""
import datetime
import os
import sys
import uuid
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.db import Base
from app.models.client import Client
from app.models.ai_check import AiCheckRun, AiCheckAnswer
from app.models.seeded_entity import SeededEntity
from app.models.risk import RiskEvent
import app.api.endpoints.client_intelligence as ci
from app.services.ai_check import service as svc
from app.services.ai_check.prompts import build_prompts, PROMPT_DEFS, REPEATS
from app.services.ai_check.reliability import classify_domain, domain_of


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
def _flag_and_key(monkeypatch):
    monkeypatch.setenv("AI_CHECK_ENABLED", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.delenv("AI_CHECK_COST_CAP_USD", raising=False)


def _client(db, name="Godrej Properties"):
    c = Client(id=uuid.uuid4(), name=name)
    db.add(c)
    db.commit()
    return c


ADMIN = SimpleNamespace(role="super_admin")
VIEWER = SimpleNamespace(role="client_user")


# ---- prompts ------------------------------------------------------------------------------------------------------------
def test_eight_questions_in_the_requested_order():
    ps = build_prompts("Acme")
    assert [p["key"] for p in ps] == ["trustworthy", "legal_controversies", "regulatory_penalties", "main_case",
                                     "customer_complaints", "delivery_delays", "vs_competitors", "safe_to_invest"]
    assert len(PROMPT_DEFS) == 8 and REPEATS == 3
    assert all("Acme" in p["text"] for p in ps)


def test_seeded_leaders_and_rivals_go_into_the_questions_they_belong_to():
    ps = {p["key"]: p["text"] for p in build_prompts("Acme", ["A One", "B Two", "C Three", "D Four"], ["Rival X", "Rival Y"])}
    assert "A One, B Two, C Three" in ps["legal_controversies"] and "D Four" not in ps["legal_controversies"]
    assert "Rival X, Rival Y" in ps["vs_competitors"]
    assert "leaders" not in ps["customer_complaints"]
    plain = {p["key"]: p["text"] for p in build_prompts("Acme")}
    assert "leaders" not in plain["legal_controversies"] and "its main competitors" in plain["vs_competitors"]


# ---- reliability ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("domain,tier,low", [
    ("www.economictimes.indiatimes.com", "high", False),
    ("livemint.com", "high", False),
    ("indianexpress.com", "medium", False),
    ("hindustantimes.com", "medium", False),
    ("thehindu.com", "medium", False),
    ("bwbusinessworld.com", "low", True),
    ("inventiva.co.in", "low", True),
    ("sproutsnews.com", "low", True),
    ("quora.com", "user_generated", True),
    ("consumercomplaints.in", "user_generated", True),
    ("youtube.com", "user_generated", True),
    ("nsearchives.nseindia.com", "official", False),
    ("dprcg.gov.in", "official", False),
    ("godrejproperties.com", "own", False),
    ("squaremind.in", "unrated", True),
    ("", "unrated", True),
])
def test_domain_reliability(domain, tier, low):
    r = classify_domain(domain, "Godrej Properties")
    assert (r["tier"], r["low_reliability"]) == (tier, low)


def test_domain_of_strips_www_and_rejects_junk():
    assert domain_of("https://www.Livemint.com/a/b?x=1") == "livemint.com"
    assert domain_of("::::") in (None, "::::") or isinstance(domain_of("::::"), str)      # never raises
    assert domain_of(None) is None and domain_of("") is None


def test_own_site_is_only_the_clients_own_name():
    assert classify_domain("easemytrip.com", "EaseMyTrip")["tier"] == "own"
    assert classify_domain("easemytrip.com", "Godrej Properties")["tier"] == "unrated"


# ---- the web call ---------------------------------------------------------------------------------------------------------
class _Resp:
    def __init__(self, text="Answer text.", urls=("https://a.com/1", "https://b.com/2"), status=200, cost=0.0133):
        self.status_code = status
        self._d = {"choices": [{"message": {"content": text, "annotations": [
            {"url_citation": {"url": u, "title": "t " + u}} for u in urls]}}], "usage": {"cost": cost, "prompt_tokens": 2700, "completion_tokens": 700}}
        self.text = "boom"

    def json(self):
        return self._d


def test_web_call_uses_the_existing_model_with_five_web_results_at_temperature_zero():
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, body=json)
        return _Resp(urls=("https://a.com/1", "https://a.com/1", "https://b.com/2"))

    r = svc.ask_with_web("Q?", "k", post=post)
    b = seen["body"]
    assert b["model"] == "anthropic/claude-haiku-4.5" and b["temperature"] == 0
    assert b["plugins"] == [{"id": "web", "max_results": 5}] and b["usage"] == {"include": True}
    assert [c["url"] for c in r["citations"]] == ["https://a.com/1", "https://b.com/2"]        # de-duplicated, order kept
    assert r["cost_usd"] == 0.0133 and r["prompt_tokens"] == 2700


@pytest.mark.parametrize("resp", [_Resp(status=500), _Resp(text="   ")])
def test_web_call_failures_raise(resp):
    with pytest.raises(svc.AiCheckCallError):
        svc.ask_with_web("Q?", "k", post=lambda *a, **k: resp)


def test_web_call_network_error_raises():
    def boom(*a, **k):
        raise RuntimeError("down")
    with pytest.raises(svc.AiCheckCallError):
        svc.ask_with_web("Q?", "k", post=boom)


# ---- estimate ---------------------------------------------------------------------------------------------------------------
def test_estimate_is_24_calls_and_under_the_cap():
    e = svc.estimate()
    assert e["calls"] == 24 and e["prompts"] == 8 and e["repeats"] == 3
    assert 0.30 < e["estimated_cost_usd"] < 0.35 and e["estimated_cost_usd"] < e["cap_usd"] == 0.60


# ---- a run --------------------------------------------------------------------------------------------------------------------
def _run(db, client, post, cap=None):
    prompts = build_prompts(client.name)
    run = svc.start_run(db, client.id, len(prompts))
    svc.execute_run(db, run, prompts, "k", post=post, cap_usd=cap)
    return run


def test_a_full_run_stores_24_answers_with_urls_domains_and_the_measured_cost(db):
    c = _client(db)
    run = _run(db, c, lambda *a, **k: _Resp(cost=0.0125))
    assert (run.status, run.calls_ok, run.calls_failed) == ("completed", 24, 0)
    assert run.cost_usd == pytest.approx(24 * 0.0125) and run.finished_at is not None
    rows = db.query(AiCheckAnswer).filter(AiCheckAnswer.run_id == run.id).all()
    assert len(rows) == 24 and {r.repeat_index for r in rows} == {0, 1, 2} and len({r.prompt_key for r in rows}) == 8
    assert rows[0].cited_domains == ["a.com", "b.com"] and rows[0].cited_urls[0]["url"] == "https://a.com/1"
    assert rows[0].prompt_text.startswith(("Is Godrej", "What", "Has", "Does", "How"))


def test_the_cost_cap_stops_the_run_before_the_next_call_would_pass_it(db):
    c = _client(db)
    calls = []
    run = _run(db, c, lambda *a, **k: calls.append(1) or _Resp(cost=0.02), cap=0.07)
    assert run.status == "stopped_at_cap" and run.cost_usd <= 0.07 and len(calls) == run.calls_ok < 24


def test_default_cap_is_sixty_cents_and_a_normal_run_stays_under_it(db, monkeypatch):
    assert svc.cost_cap_usd() == 0.60
    monkeypatch.setenv("AI_CHECK_COST_CAP_USD", "0.10")
    assert svc.cost_cap_usd() == 0.10
    monkeypatch.setenv("AI_CHECK_COST_CAP_USD", "junk")
    assert svc.cost_cap_usd() == 0.60


def test_one_failed_call_does_not_stop_the_run_but_repeated_failures_do(db):
    c = _client(db)
    n = {"i": 0}

    def flaky(*a, **k):
        n["i"] += 1
        return _Resp(status=500) if n["i"] == 3 else _Resp()

    run = _run(db, c, flaky)
    assert (run.status, run.calls_ok, run.calls_failed) == ("completed", 23, 1) and run.error

    c2 = _client(db, "Other")
    dead = _run(db, c2, lambda *a, **k: _Resp(status=500))
    assert dead.status == "failed" and dead.calls_ok == 0 and dead.calls_failed == 4          # gave up after 4 in a row, not 24


def test_a_run_touches_no_score_table(db):
    c = _client(db)
    _run(db, c, lambda *a, **k: _Resp())
    assert db.query(RiskEvent).count() == 0


# ---- read-back ----------------------------------------------------------------------------------------------------------------
def test_short_answer_drops_markdown_headings_and_links_and_cuts_at_a_sentence():
    text = "# Godrej Legal\n\n## Strengths\n\nGodrej is listed and files [audited results](https://x.com) every quarter. " + "It also has a very long sentence that goes on. " * 20
    s = svc.short_answer(text)
    assert "#" not in s and "https" not in s and "audited results" in s and len(s) <= 322 and s.endswith((".", "…"))


def _answer(db, run, key, rep, urls, text="Plain answer text here, which is long enough to be a sentence."):
    db.add(AiCheckAnswer(id=uuid.uuid4(), run_id=run.id, client_id=run.client_id, prompt_key=key, prompt_text="Q " + key,
                         repeat_index=rep, answer_text=text, cited_urls=[{"url": u, "title": "T " + u} for u in urls],
                         cited_domains=sorted({domain_of(u) for u in urls}), cost_usd=0.01))
    db.commit()


def test_stability_marker_same_pages_vs_changed_pages(db):
    c = _client(db)
    run = svc.start_run(db, c.id)
    for rep in range(3):
        _answer(db, run, "trustworthy", rep, ["https://livemint.com/a", "https://squaremind.in/b"])
    for rep, extra in enumerate(["https://x.com/1", "https://x.com/2", "https://x.com/3"]):
        _answer(db, run, "legal_controversies", rep, ["https://livemint.com/a", extra])
    rep_ = svc.latest_report(db, c)
    by = {p["key"]: p for p in rep_["prompts"]}
    assert by["trustworthy"]["stable"] is True and by["trustworthy"]["stability"] == "Same pages cited in all 3 runs."
    assert by["legal_controversies"]["stable"] is False and "changed" in by["legal_controversies"]["stability"]
    assert [p["key"] for p in rep_["prompts"]] == ["trustworthy", "legal_controversies"]           # card order = question order


def test_cited_domains_carry_their_reliability_and_the_low_reliability_pages_are_listed(db):
    c = _client(db)
    run = svc.start_run(db, c.id)
    for rep in range(3):
        _answer(db, run, "legal_controversies", rep, ["https://economictimes.indiatimes.com/a", "https://www.inventiva.co.in/story", "https://quora.com/q"])
    _answer(db, run, "trustworthy", 0, ["https://www.inventiva.co.in/story", "https://hindustantimes.com/z"])
    out = svc.latest_report(db, c, is_admin=False)
    src = {s["domain"]: s for s in out["prompts"][1]["sources"]} if out["prompts"][0]["key"] == "trustworthy" else {s["domain"]: s for s in out["prompts"][0]["sources"]}
    assert src["economictimes.indiatimes.com"]["reliability"] == "High" and src["inventiva.co.in"]["reliability"] == "Low"
    assert src["quora.com"]["low_reliability"] is True and src["economictimes.indiatimes.com"]["low_reliability"] is False
    pages = {p["url"]: p for p in out["low_reliability_pages"]}
    assert set(pages) == {"https://www.inventiva.co.in/story", "https://quora.com/q"}
    inv = pages["https://www.inventiva.co.in/story"]
    assert inv["cited_in_answers"] == 4 and sorted(inv["questions"]) == ["Is it trustworthy?", "Legal cases and controversies"] and inv["title"]
    assert out["low_reliability_pages"][0]["url"] == "https://www.inventiva.co.in/story"       # most-cited first
    assert out["removal_candidates"] == []                                                        # not for a non-admin


def test_removal_candidates_are_returned_to_super_admins_only(db):
    c = _client(db)
    run = svc.start_run(db, c.id)
    _answer(db, run, "trustworthy", 0, ["https://www.inventiva.co.in/story"])
    assert [p["url"] for p in svc.latest_report(db, c, is_admin=True)["removal_candidates"]] == ["https://www.inventiva.co.in/story"]
    assert svc.latest_report(db, c, is_admin=False)["removal_candidates"] == []


def test_report_with_no_run_yet(db):
    c = _client(db)
    r = svc.latest_report(db, c)
    assert r["run"] is None and r["prompts"] == [] and r["enabled"] is True


# ---- endpoints ----------------------------------------------------------------------------------------------------------------
def test_get_is_off_by_default_and_hides_removal_list_from_viewers(db, monkeypatch):
    c = _client(db)
    monkeypatch.delenv("AI_CHECK_ENABLED")
    assert ci.get_client_ai_check(c.id, db, VIEWER) == {"enabled": False}
    monkeypatch.setenv("AI_CHECK_ENABLED", "1")
    run = svc.start_run(db, c.id)
    _answer(db, run, "trustworthy", 0, ["https://www.inventiva.co.in/story"])
    v = ci.get_client_ai_check(c.id, db, VIEWER)
    a = ci.get_client_ai_check(c.id, db, ADMIN)
    assert v["can_run"] is False and v["removal_candidates"] == [] and len(v["low_reliability_pages"]) == 1
    assert a["can_run"] is True and len(a["removal_candidates"]) == 1 and a["estimate"]["calls"] == 24


def test_post_is_refused_when_the_flag_is_off(db, monkeypatch):
    c = _client(db)
    monkeypatch.delenv("AI_CHECK_ENABLED")
    with pytest.raises(HTTPException) as e:
        ci.run_client_ai_check(c.id, BackgroundTasks(), True, db, ADMIN)
    assert e.value.status_code == 409


def test_dry_run_prints_the_estimate_and_questions_and_stores_nothing(db):
    c = _client(db)
    db.add(SeededEntity(id=uuid.uuid4(), client_id=c.id, kind="executive", name="Pirojsha Godrej", rank=1, status="active"))
    db.add(SeededEntity(id=uuid.uuid4(), client_id=c.id, kind="competitor", name="DLF Limited", rank=1, status="active"))
    db.add(SeededEntity(id=uuid.uuid4(), client_id=c.id, kind="executive", name="Retired Person", rank=2, status="retired"))
    db.commit()
    r = ci.run_client_ai_check(c.id, BackgroundTasks(), True, db, ADMIN)
    assert r["dry_run"] is True and r["estimate"]["calls"] == 24
    texts = {q["key"]: q["text"] for q in r["questions"]}
    assert "Pirojsha Godrej" in texts["legal_controversies"] and "Retired Person" not in texts["legal_controversies"]
    assert "DLF Limited" in texts["vs_competitors"]
    assert db.query(AiCheckRun).count() == 0


def test_real_run_starts_in_the_background_and_a_second_start_is_refused(db):
    c = _client(db)
    bg = BackgroundTasks()
    r = ci.run_client_ai_check(c.id, bg, False, db, ADMIN)
    assert r["dry_run"] is False and r["status"] == "running" and len(bg.tasks) == 1
    assert db.query(AiCheckRun).filter(AiCheckRun.id == uuid.UUID(r["run_id"])).one().estimated_cost_usd == r["estimate"]["estimated_cost_usd"]
    with pytest.raises(HTTPException) as e:
        ci.run_client_ai_check(c.id, BackgroundTasks(), False, db, ADMIN)
    assert e.value.status_code == 409
    # a run left "running" long ago does not block a new one
    old = db.query(AiCheckRun).one()
    old.started_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=svc.RUN_STALE_MINUTES + 5)
    db.commit()
    assert ci.run_client_ai_check(c.id, BackgroundTasks(), False, db, ADMIN)["status"] == "running"


def test_missing_key_is_a_503_before_anything_is_stored(db, monkeypatch):
    c = _client(db)
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(HTTPException) as e:
        ci.run_client_ai_check(c.id, BackgroundTasks(), False, db, ADMIN)
    assert e.value.status_code == 503 and db.query(AiCheckRun).count() == 0


def test_unknown_client_is_404(db):
    with pytest.raises(HTTPException) as e:
        ci.get_client_ai_check(uuid.uuid4(), db, ADMIN)
    assert e.value.status_code == 404


def test_post_requires_a_super_admin_in_the_route_definition():
    from fastapi.routing import APIRoute
    from app.core.auth import require_super_admin
    route = next(r for r in ci.router.routes if isinstance(r, APIRoute) and r.path == "/{client_id}/ai-check/run" and "POST" in r.methods)
    assert any(d.call is require_super_admin for d in route.dependant.dependencies)
