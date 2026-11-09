"""Run Pipeline cost meter (services/pipeline_cost.py): Apify usage, LLM calls and tokens with an estimated dollar cost, search calls.
In-memory SQLite only; the Apify HTTP calls are faked. Nothing here reaches Apify, OpenRouter or a real database."""
import datetime
import os
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityKeyword
from app.models.pipeline_run import PipelineRun
from app.models.pipeline_run_cost import PipelineRunCost
from app.models.search import SearchCursor
import app.api.endpoints.client_intelligence as ci
from app.services import pipeline_cost as pc


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
    # llm_call_log has no ORM model (it is written with raw SQL by utils/llm_call_logging.py), so the test creates the table.
    session.execute(text("CREATE TABLE llm_call_log (id TEXT, call_type TEXT, client_id TEXT, run_id TEXT, tokens_prompt INTEGER, "
                         "tokens_completion INTEGER, latency_ms REAL, success BOOLEAN, created_at TIMESTAMP)"))
    session.commit()
    yield session
    session.close()


def _client(db, name="Godrej Properties"):
    c = Client(id=uuid.uuid4(), name=name)
    db.add(c)
    db.commit()
    return c


# ---- LLM price ----------------------------------------------------------------------------------------------------------------
def test_llm_cost_uses_the_public_per_token_price_of_the_model_each_call_type_uses():
    assert pc.llm_cost_usd("risk_case_status", 1_000_000, 1_000_000) == pytest.approx(6.0)           # Haiku 4.5: $1 in, $5 out
    assert pc.llm_cost_usd("risk_penalty_parse", 260, 25) == pytest.approx(0.000385)
    assert pc.llm_cost_usd("risk_role_classify", 1_000_000, 0) == pytest.approx(0.95526)             # deepseek-v4-pro
    assert pc.llm_cost_usd("something_new", 100, 100) is None                                          # no listed price: not guessed
    assert pc.llm_cost_usd("risk_case_status", 0, 0) == 0.0 and pc.llm_cost_usd("risk_case_status", None, None) == 0.0


# ---- Apify ----------------------------------------------------------------------------------------------------------------------
def test_apify_usage_accumulates_per_source_and_flags_estimates(db):
    c = _client(db)
    assert pc.record_apify_usage("run1", c.id, "reddit", 0.056, False, db=db)
    assert pc.record_apify_usage("run1", c.id, "reddit", 0.044, False, db=db)
    assert pc.record_apify_usage("run1", c.id, "instagram", 0.0675, True, db=db)
    row = db.query(PipelineRunCost).one()
    assert (row.apify_calls, row.apify_cost_usd, row.apify_cost_estimated) == (3, pytest.approx(0.1675), True)
    assert row.apify_by_source["reddit"] == {"calls": 2, "usd": pytest.approx(0.1), "estimated": False}
    assert row.apify_by_source["instagram"] == {"calls": 1, "usd": pytest.approx(0.0675), "estimated": True}


def test_an_unreadable_cost_is_counted_costs_nothing_and_flags_the_total_as_estimated(db):
    c = _client(db)
    pc.record_apify_usage("run1", c.id, "reddit", None, False, db=db)
    row = db.query(PipelineRunCost).one()
    assert (row.apify_calls, row.apify_cost_usd, row.apify_cost_estimated) == (1, 0.0, True)


def test_reddit_cost_is_the_actors_reported_usage_and_instagram_is_estimated_from_the_result_count(db):
    c = _client(db)
    pc.record_social_search("run1", c.id, "reddit", SimpleNamespace(last_usage_usd=0.056), 4, db=db)
    pc.record_social_search("run1", c.id, "instagram", SimpleNamespace(), 25, db=db)
    pc.record_social_search("run2", c.id, "reddit", SimpleNamespace(last_usage_usd=None), 4, db=db)
    r1 = db.query(PipelineRunCost).filter_by(run_id="run1").one()
    assert r1.apify_by_source["reddit"]["usd"] == pytest.approx(0.056) and r1.apify_by_source["reddit"]["estimated"] is False
    assert r1.apify_by_source["instagram"]["usd"] == pytest.approx(25 * 0.0027) and r1.apify_by_source["instagram"]["estimated"] is True
    assert db.query(PipelineRunCost).filter_by(run_id="run2").one().apify_cost_estimated is True


def test_recording_never_raises_into_a_pipeline_stage():
    broken = MagicMock()
    broken.query.side_effect = RuntimeError("db down")
    assert pc.record_apify_usage("run1", uuid.uuid4(), "reddit", 0.1, False, db=broken) is False
    assert pc.record_social_search("run1", uuid.uuid4(), "reddit", SimpleNamespace(last_usage_usd=0.1), 1, db=broken) is False
    assert pc.finalize_run_cost("run1", uuid.uuid4(), db=broken) is False


def test_reddit_adapter_exposes_the_finished_runs_usage(monkeypatch):
    import app.adapters.reddit_apify as ra

    class R:
        def __init__(self, data, status=200):
            self._d, self.status_code, self.text = data, status, ""

        def json(self):
            return self._d

    monkeypatch.setenv("APIFY_API_TOKEN", "test-not-real")
    monkeypatch.setattr(ra.time, "sleep", lambda s: None)
    monkeypatch.setattr(ra.requests, "post", lambda *a, **k: R({"data": {"id": "run9", "status": "RUNNING", "defaultDatasetId": "ds1"}}))
    polls = iter([R({"data": {"status": "RUNNING", "defaultDatasetId": "ds1"}}), R({"data": {"status": "SUCCEEDED", "defaultDatasetId": "ds1", "usageTotalUsd": 0.056}})])

    def get(url, *a, **k):
        return next(polls) if "actor-runs" in url else R([{"title": "Godrej Properties news", "body": "x", "url": "https://r/1"}])

    monkeypatch.setattr(ra.requests, "get", get)
    a = ra.RedditApifyAdapter()
    assert a.last_usage_usd is None
    items, cursor = a.search("Godrej Properties")
    assert len(items) == 1 and cursor is None and a.last_usage_usd == pytest.approx(0.056)


def test_reddit_adapter_leaves_usage_empty_when_apify_does_not_report_it(monkeypatch):
    import app.adapters.reddit_apify as ra

    class R:
        status_code, text = 200, ""

        def __init__(self, data):
            self._d = data

        def json(self):
            return self._d

    monkeypatch.setenv("APIFY_API_TOKEN", "test-not-real")
    monkeypatch.setattr(ra.requests, "post", lambda *a, **k: R({"data": {"id": "run9", "status": "SUCCEEDED", "defaultDatasetId": "ds1"}}))
    monkeypatch.setattr(ra.requests, "get", lambda *a, **k: R([]))
    a = ra.RedditApifyAdapter()
    a.search("Godrej Properties")
    assert a.last_usage_usd is None


# ---- finalize: LLM and search figures ---------------------------------------------------------------------------------------------
def _llm(db, client_id, call_type, when, tp=100, tc=10, ok=True):
    db.execute(text("INSERT INTO llm_call_log (id, call_type, client_id, run_id, tokens_prompt, tokens_completion, success, created_at) "
                    "VALUES (:i, :t, :c, 'r', :p, :q, :s, :w)"),
               {"i": str(uuid.uuid4()), "t": call_type, "c": str(client_id), "p": tp, "q": tc, "s": ok, "w": when})
    db.commit()


def _search(db, client, source, when, name="Godrej Properties"):
    ent = db.query(Entity).filter(Entity.client_id == client.id).first() or Entity(id=uuid.uuid4(), client_id=client.id, name=name, entity_type="brand")
    db.add(ent)
    db.commit()
    kw = EntityKeyword(id=uuid.uuid4(), entity_id=ent.id, keyword_text=name + source, category="PRIMARY")
    db.add(kw)
    db.commit()
    db.add(SearchCursor(keyword_id=kw.id, source_type=source, last_searched_at=when))
    db.commit()


def test_finalize_sums_the_runs_llm_calls_by_type_prices_them_and_counts_searches(db):
    c, other = _client(db), _client(db, "EaseMyTrip")
    t0 = datetime.datetime(2026, 11, 9, 10, 0, tzinfo=datetime.timezone.utc)
    db.add(PipelineRun(client_id=str(c.id), run_id="run1", status="SUCCESS", stage="SUCCESS", progress_pct=100, started_at=t0))
    db.commit()
    mins = lambda m: (t0 + datetime.timedelta(minutes=m)).replace(tzinfo=None)
    _llm(db, c.id, "risk_case_status", mins(5), 260, 25)
    _llm(db, c.id, "risk_case_status", mins(6), 240, 25, ok=False)
    _llm(db, c.id, "risk_role_classify", mins(7), 500, 10)
    _llm(db, c.id, "brand_new_call", mins(8), 100, 100)
    _llm(db, c.id, "risk_case_status", mins(-30), 999, 99)            # before the run started: not this run's
    _llm(db, other.id, "risk_case_status", mins(6), 999, 99)         # another client's
    _search(db, c, "youtube", t0 + datetime.timedelta(minutes=2))
    _search(db, c, "reddit", t0 + datetime.timedelta(minutes=3))
    _search(db, c, "reddit", t0 - datetime.timedelta(days=1))        # an earlier run's search
    _search(db, other, "youtube", t0 + datetime.timedelta(minutes=2), name="EaseMyTrip")
    pc.record_apify_usage("run1", c.id, "reddit", 0.056, False, db=db)
    assert pc.finalize_run_cost("run1", c.id, db=db, now=t0 + datetime.timedelta(minutes=20))
    row = db.query(PipelineRunCost).one()
    assert row.finalized is True and row.apify_cost_usd == pytest.approx(0.056)                       # Apify figures kept
    assert (row.llm_calls, row.llm_tokens_prompt, row.llm_tokens_completion) == (4, 1100, 160)
    cs = row.llm_by_type["risk_case_status"]
    assert (cs["calls"], cs["failed"], cs["tokens_prompt"], cs["price_known"]) == (2, 1, 500, True)
    assert cs["est_usd"] == pytest.approx((500 * 1.0 + 50 * 5.0) / 1e6)
    assert row.llm_by_type["brand_new_call"]["price_known"] is False and row.llm_by_type["brand_new_call"]["est_usd"] == 0.0
    expected = (500 * 1.0 + 50 * 5.0) / 1e6 + (500 * 0.95526 + 10 * 1.91052) / 1e6
    assert row.llm_est_cost_usd == pytest.approx(expected, abs=2e-6)
    assert row.search_calls == 2 and row.search_by_source == {"youtube": 1, "reddit": 1}


def test_finalize_without_apify_calls_still_creates_the_row(db):
    c = _client(db)
    assert pc.finalize_run_cost("run-x", c.id, db=db)
    row = db.query(PipelineRunCost).one()
    assert (row.finalized, row.apify_calls, row.llm_calls, row.search_calls) == (True, 0, 0, 0)


# ---- reading it back --------------------------------------------------------------------------------------------------------------
def test_last_run_cost_returns_the_latest_row_with_the_runs_status_and_a_total(db):
    c = _client(db)
    assert pc.last_run_cost(db, c.id) is None
    t0 = datetime.datetime(2026, 11, 9, 10, 0, tzinfo=datetime.timezone.utc)
    db.add(PipelineRun(client_id=str(c.id), run_id="old", status="SUCCESS", stage="SUCCESS", progress_pct=100, started_at=t0))
    db.add(PipelineRun(client_id=str(c.id), run_id="new", status="SUCCESS", stage="SUCCESS", progress_pct=100, started_at=t0 + datetime.timedelta(hours=1)))
    db.commit()
    pc.record_apify_usage("old", c.id, "reddit", 0.5, False, db=db)
    old = db.query(PipelineRunCost).filter_by(run_id="old").one()
    old.created_at = t0
    db.commit()
    pc.record_apify_usage("new", c.id, "reddit", 0.056, False, db=db)
    db.query(PipelineRunCost).filter_by(run_id="new").one().created_at = t0 + datetime.timedelta(hours=1)
    db.commit()
    pc.finalize_run_cost("new", c.id, db=db, now=t0 + datetime.timedelta(hours=2))
    r = pc.last_run_cost(db, c.id)
    assert r["run_id"] == "new" and r["finalized"] is True and r["run"]["status"] == "SUCCESS"
    assert r["apify"]["cost_usd"] == pytest.approx(0.056) and r["apify"]["by_source"]["reddit"]["calls"] == 1
    assert r["total_usd"] == pytest.approx(0.056 + r["llm"]["est_cost_usd"])


def test_endpoint_is_super_admin_only_in_its_route_definition_and_404s_an_unknown_client(db):
    from app.core.auth import require_super_admin
    route = next(r for r in ci.router.routes if isinstance(r, APIRoute) and r.path == "/{client_id}/pipeline-cost" and "GET" in r.methods)
    assert any(d.call is require_super_admin for d in route.dependant.dependencies)
    c = _client(db)
    assert ci.get_client_pipeline_cost(c.id, db, None) == {"last_run": None}
    pc.record_apify_usage("r1", c.id, "reddit", 0.056, False, db=db)
    assert ci.get_client_pipeline_cost(c.id, db, None)["last_run"]["apify"]["calls"] == 1
    with pytest.raises(HTTPException) as e:
        ci.get_client_pipeline_cost(uuid.uuid4(), db, None)
    assert e.value.status_code == 404


# ---- the pipeline stages are not affected by a metering failure --------------------------------------------------------------------
def test_finalize_stage_still_completes_when_the_meter_fails(monkeypatch):
    import app.workers.aggregation_tasks as at
    monkeypatch.setattr(pc, "finalize_run_cost", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("meter down")))
    db = MagicMock()
    ctx = SimpleNamespace(run_id="r1", client_id=str(uuid.uuid4()), worker_id="w")
    at._stage_finalize(ctx, db)
    db.commit.assert_called()


def test_finalize_stage_calls_the_meter_with_the_runs_ids(monkeypatch):
    import app.workers.aggregation_tasks as at
    seen = []
    monkeypatch.setattr(pc, "finalize_run_cost", lambda run_id, client_id, **k: seen.append((run_id, client_id)) or True)
    cid = str(uuid.uuid4())
    at._stage_finalize(SimpleNamespace(run_id="r1", client_id=cid, worker_id="w"), MagicMock())
    assert seen == [("r1", cid)]
