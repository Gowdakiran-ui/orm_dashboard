"""Competitors tab audit fixes (audit/competitors-audit.md F-02, F-03, F-11): `GET /competitor-search`.

In-memory SQLite only; Redis and Celery are replaced by small fakes, DATABASE_URL is an unreachable dummy,
so nothing here can reach a real database, queue or LLM.
"""
import os
import sys
import uuid
import datetime
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
from app.models.entity import Entity
from app.models.rss_feed import RSSFeed
from app.models.collection_job import CollectionJob
from app.models.competitor_benchmark import CompetitorBenchmark
from app.models.pipeline_run import PipelineRun
from app.services.client_service import competitor_search_feed_urls
import app.api.endpoints.client_intelligence as ci


@compiles(PG_UUID, "sqlite")
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)


class FakeCelery:
    def __init__(self):
        self.sent = []

    def send_task(self, name, args=None, **kw):
        self.sent.append((name, args))


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    redis, celery = FakeRedis(), FakeCelery()
    import app.utils.redis_client as rc
    import app.core.celery_app as ca
    monkeypatch.setattr(rc, "redis_client", redis)
    monkeypatch.setattr(ca, "celery_app", celery)
    yield SimpleNamespace(db=session, redis=redis, celery=celery)
    session.close()


def _client(db):
    c = Client(id=uuid.uuid4(), name=f"Acme-{uuid.uuid4().hex[:6]}")
    db.add(c)
    db.commit()
    return c.id


def _competitor(db, cid, name):
    e = Entity(id=uuid.uuid4(), client_id=cid, name=name, entity_type="competitor")
    db.add(e)
    db.commit()
    return e


def _feeds_with_finished_jobs(db, cid, name):
    for url in competitor_search_feed_urls(name).values():
        f = RSSFeed(id=uuid.uuid4(), feed_name=f"{name} feed", feed_url=url, client_id=cid, source_type="entity_search", source_format="rss")
        db.add(f)
        db.commit()
        db.add(CollectionJob(job_id=uuid.uuid4(), source_id=f.id, status="completed"))
        db.commit()


def _bench(db, cid, ent, health, rep, sent=0.4, risk=3.0, sov=1.5, mentions=7.0, rank=2, when=None):
    b = CompetitorBenchmark(id=uuid.uuid4(), client_id=cid, competitor_entity_id=ent.id, reputation_score=rep, sentiment_score=sent,
                            risk_score=risk, visibility_score=mentions, share_of_voice=sov, rank=rank, run_id="r1", health_status=health,
                            confidence_score=0.5, data_coverage=0.5)
    if when:
        b.created_at = when
    db.add(b)
    db.commit()
    return b


def _search(env, cid, name):
    return ci.search_client_competitor(cid, name, env.db)


# ---------------------------------------------------------------------------
# F-02: a no-evidence row never reaches the page as a measurement
# ---------------------------------------------------------------------------
def test_no_evidence_row_is_served_as_nulls_not_zeros(env):
    cid = _client(env.db)
    e = _competitor(env.db, cid, "M3M")
    _bench(env.db, cid, e, "INSUFFICIENT_EVIDENCE", 0.0, sent=0.0, risk=0.0, sov=0.0, mentions=0.0, rank=0)
    out = _search(env, cid, "M3M")
    c = out["competitor"]
    assert out["status"] == "tracked" and c["health_status"] == "INSUFFICIENT_EVIDENCE"
    for k in ("reputation_score", "sentiment_score", "risk_score", "share_of_voice", "confidence_score", "data_coverage", "mentions_30d"):
        assert c[k] is None, k


def test_scored_row_keeps_its_values_and_adds_mentions_and_as_of(env):
    cid = _client(env.db)
    e = _competitor(env.db, cid, "EMAAR")
    when = datetime.datetime(2026, 10, 2, 8, 46, tzinfo=datetime.timezone.utc)
    _bench(env.db, cid, e, "COMPLETE", 93.33, sent=1.0, risk=0.0, sov=0.155, mentions=1.0, rank=1, when=when)
    c = _search(env, cid, "EMAAR")["competitor"]
    assert c["reputation_score"] == 93.33 and c["sentiment_score"] == 1.0 and c["risk_score"] == 0.0   # a measured 0.0 stays 0.0
    assert c["share_of_voice"] == 0.155 and c["rank"] == 1
    assert c["mentions_30d"] == 1.0
    assert c["as_of"].startswith("2026-10-02")


def test_measured_zero_risk_is_not_confused_with_no_evidence(env):
    cid = _client(env.db)
    e = _competitor(env.db, cid, "Tata")
    _bench(env.db, cid, e, "COMPLETE", 90.0, risk=0.0)
    assert _search(env, cid, "Tata")["competitor"]["risk_score"] == 0.0


# ---------------------------------------------------------------------------
# F-03: a tracked entity the engine never scores must not loop forever
# ---------------------------------------------------------------------------
def test_unscored_entity_dispatches_once_then_reports_no_coverage(env):
    cid = _client(env.db)
    e = _competitor(env.db, cid, "Relianca")
    _feeds_with_finished_jobs(env.db, cid, "Relianca")

    first = _search(env, cid, "Relianca")
    assert first == {"status": "searching"}
    assert len(env.celery.sent) == 1                       # the one dispatch

    # the task is still running (in-flight key set): polling must not dispatch again
    for _ in range(5):
        assert _search(env, cid, "Relianca") == {"status": "searching"}
    assert len(env.celery.sent) == 1

    # the task finished (it deletes the in-flight key) and the engine wrote no row for this entity
    env.redis.delete(f"competitor_search_processing:{cid}")
    done = _search(env, cid, "Relianca")
    assert done["status"] == "tracked"
    assert done["competitor"]["health_status"] == "INSUFFICIENT_EVIDENCE"
    assert done["competitor"]["reason"] == "no_coverage_mentioning_client"
    assert done["competitor"]["reputation_score"] is None
    for _ in range(5):                                     # and it stays terminal: no new runs
        _search(env, cid, "Relianca")
    assert len(env.celery.sent) == 1


def test_entity_scored_by_the_run_is_returned_as_tracked_with_values(env):
    cid = _client(env.db)
    e = _competitor(env.db, cid, "Newco")
    _feeds_with_finished_jobs(env.db, cid, "Newco")
    assert _search(env, cid, "Newco") == {"status": "searching"}
    _bench(env.db, cid, e, "COMPLETE", 71.0, mentions=4.0)       # the run wrote a row
    env.redis.delete(f"competitor_search_processing:{cid}")
    out = _search(env, cid, "Newco")
    assert out["competitor"]["reputation_score"] == 71.0 and out["competitor"].get("reason") is None
    assert len(env.celery.sent) == 1


def test_still_collecting_feeds_report_searching_without_dispatch(env):
    cid = _client(env.db)
    _competitor(env.db, cid, "Slowco")
    for url in competitor_search_feed_urls("Slowco").values():
        f = RSSFeed(id=uuid.uuid4(), feed_name="f", feed_url=url, client_id=cid, source_type="entity_search", source_format="rss")
        env.db.add(f)
        env.db.commit()
        env.db.add(CollectionJob(job_id=uuid.uuid4(), source_id=f.id, status="processing"))
        env.db.commit()
    assert _search(env, cid, "Slowco") == {"status": "searching"}
    assert env.celery.sent == []


def test_no_trend_words_in_the_search_payload(env):
    cid = _client(env.db)
    e = _competitor(env.db, cid, "EMAAR")
    _bench(env.db, cid, e, "COMPLETE", 80.0)
    text = repr(_search(env, cid, "EMAAR")).lower()
    for w in ("trend", "improving", "declining", "steady", "stable"):
        assert w not in text


# ---------------------------------------------------------------------------
# Round 2: never dispatch while ANY pipeline run for the client is active
# ---------------------------------------------------------------------------
def _pipeline_run(db, cid, status, stage=None):
    db.add(PipelineRun(id=uuid.uuid4(), client_id=str(cid), run_id=uuid.uuid4().hex, status=status, stage=stage or status))
    db.commit()


@pytest.mark.parametrize("status", ["QUEUED", "COLLECTING", "AWAITING_PROCESSING", "PROCESSING", "RISK", "BENCHMARK", "FINALIZING"])
def test_no_dispatch_and_no_terminal_verdict_while_a_pipeline_run_is_active(env, status):
    cid = _client(env.db)
    _competitor(env.db, cid, "Relianca")
    _feeds_with_finished_jobs(env.db, cid, "Relianca")
    _pipeline_run(env.db, cid, status)
    for _ in range(4):
        assert _search(env, cid, "Relianca") == {"status": "searching"}
    assert env.celery.sent == []
    assert env.redis.get(f"competitor_search_processing:{cid}") is None      # nothing was claimed
    assert not any(k.startswith("competitor_search_dispatched:") for k in env.redis.store)


def test_dispatch_happens_once_the_pipeline_run_has_finished(env):
    cid = _client(env.db)
    _competitor(env.db, cid, "Relianca")
    _feeds_with_finished_jobs(env.db, cid, "Relianca")
    _pipeline_run(env.db, cid, "SUCCESS")
    _pipeline_run(env.db, cid, "FAILED")
    assert _search(env, cid, "Relianca") == {"status": "searching"}
    assert len(env.celery.sent) == 1


def test_another_clients_pipeline_run_does_not_block(env):
    cid = _client(env.db)
    other = _client(env.db)
    _competitor(env.db, cid, "Relianca")
    _feeds_with_finished_jobs(env.db, cid, "Relianca")
    _pipeline_run(env.db, other, "PROCESSING")
    assert _search(env, cid, "Relianca") == {"status": "searching"}
    assert len(env.celery.sent) == 1


def test_a_search_triggered_run_in_flight_blocks_a_second_dispatch_for_another_competitor(env):
    cid = _client(env.db)
    _competitor(env.db, cid, "Alpha")
    _competitor(env.db, cid, "Beta")
    _feeds_with_finished_jobs(env.db, cid, "Alpha")
    _feeds_with_finished_jobs(env.db, cid, "Beta")
    assert _search(env, cid, "Alpha") == {"status": "searching"}
    assert len(env.celery.sent) == 1
    for _ in range(3):
        assert _search(env, cid, "Beta") == {"status": "searching"}   # per-client in-flight key still set
    assert len(env.celery.sent) == 1


# ---------------------------------------------------------------------------
# Round 2: removed routes stay removed
# ---------------------------------------------------------------------------
def test_unused_share_of_voice_and_competitive_summary_routes_are_gone():
    paths = {r.path for r in ci.router.routes}
    assert not any(p.endswith("/share-of-voice") for p in paths)
    assert not any(p.endswith("/competitive-summary") for p in paths)
    assert any(p.endswith("/benchmark") for p in paths) and any(p.endswith("/competitor-search") for p in paths)
