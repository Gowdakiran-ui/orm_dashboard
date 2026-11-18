"""New-client fixes (2026-11-18): the freshness skip looks at new data, Google News failures are not "0 news",
one shared limiter and circuit breaker for Google News, pending-validation status.

In-memory SQLite and fakes only: DATABASE_URL is an unreachable dummy, no network, no Redis, no LLM.
"""
import os
import sys
import uuid
import datetime as dt

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
from app.models.entity import Entity, EntityMention
from app.models.reputation import ReputationScore
from app.models.seeded_entity import SeededEntity
from app.services.seeding import service, validator
from app.services.backfill import fetchers
from app.workers import aggregation_tasks


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


# ------------------------------------------------------------------ 1. freshness skip looks at new data
def _score_row(client_id, minutes_ago):
    return ReputationScore(id=uuid.uuid4(), client_id=client_id, score=70.0, grade="B",
                           created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago))


def _mention(db, entity, minutes_ago):
    d = Document(id=uuid.uuid4(), url=f"https://x.com/{uuid.uuid4()}", content_hash=uuid.uuid4().hex, normalized_content="x")
    db.add(d)
    db.flush()
    db.add(EntityMention(id=uuid.uuid4(), document_id=d.id, entity_id=entity.id, mention_count=1,
                         created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)))
    db.commit()


def _client_with_entity(db):
    nm = "Fresh Co " + uuid.uuid4().hex[:6]
    c = Client(id=uuid.uuid4(), name=nm)
    e = Entity(id=uuid.uuid4(), client_id=c.id, name=nm, entity_type="brand")
    db.add_all([c, e])
    db.commit()
    return c, e


def test_a_recent_score_is_skipped_only_while_no_new_mention_exists(db):
    c, e = _client_with_entity(db)
    db.add(_score_row(c.id, 10))
    db.commit()
    _mention(db, e, 60)                                    # older than the score: still fresh
    assert aggregation_tasks._stage_is_fresh_enough(db, ReputationScore, c.id, hours=2.0) is True
    _mention(db, e, 1)                                     # matched after the score was written: recompute
    assert aggregation_tasks._stage_is_fresh_enough(db, ReputationScore, c.id, hours=2.0) is False


def test_an_old_score_is_never_fresh_and_another_clients_mention_is_ignored(db):
    c, e = _client_with_entity(db)
    other, oe = _client_with_entity(db)
    db.add(_score_row(c.id, 300))
    db.commit()
    assert aggregation_tasks._stage_is_fresh_enough(db, ReputationScore, c.id, hours=2.0) is False
    db2 = _score_row(c.id, 5)
    db.add(db2)
    db.commit()
    _mention(db, oe, 1)                                    # new mention, but on the other client
    assert aggregation_tasks._stage_is_fresh_enough(db, ReputationScore, c.id, hours=2.0) is True


def test_no_score_row_is_not_fresh(db):
    c, e = _client_with_entity(db)
    assert aggregation_tasks._stage_is_fresh_enough(db, ReputationScore, c.id, hours=2.0) is False


# ------------------------------------------------------------------ 2. a failed lookup is not "0 news"
@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(validator, "GN_RETRY_DELAYS", (0.0, 0.0))


def _down(query, a, b):
    raise Exception("HTTP Error 503 fetching feed")


def test_gn_count_retries_a_failed_slice_and_reports_slices_that_stay_down():
    calls = {"n": 0}

    def flaky(query, a, b):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise Exception("HTTP Error 503")
        return [object()] * 3
    out = validator.gn_count("q", flaky)
    assert out["errors"] == 0 and out["total"] == 12 and calls["n"] == 6        # first slice needed 3 tries
    down = validator.gn_count("q", _down)
    assert down["errors"] == 4 and down["total"] == 0


def test_executive_during_an_outage_is_pending_not_rejected():
    v = validator.validate_executive({"name": "A B", "source_urls": ["https://x.com/a"]}, "Co", [], _down)
    assert v["accepted"] is False and v["pending"] is True
    assert v["reason"].startswith("pending validation (source unavailable)")
    assert not v.get("needs_better_sources")                                    # no paid follow-up for an outage


def test_executive_with_enough_news_is_accepted_even_if_one_slice_failed():
    seq = iter([Exception("503"), Exception("503"), Exception("503")])

    def one_bad_slice(q, a, b):
        try:
            raise next(seq)
        except StopIteration:
            return [object()] * 2
    v = validator.validate_executive({"name": "A B", "source_urls": ["https://x.com/a"]}, "Co", [], one_bad_slice)
    assert v["accepted"] is True and not v.get("pending")


def test_a_real_zero_is_still_a_rejection_without_pending():
    v = validator.validate_executive({"name": "A B", "source_urls": ["https://x.com/a"]}, "Co", [], lambda q, a, b: [])
    assert v["accepted"] is False and not v.get("pending") and "no Google News item" in v["reason"]


def test_competitor_during_an_outage_is_pending_and_below_threshold_without_errors_is_rejected():
    item = {"name": "DLF", "context_term": "real estate"}
    v = validator.validate_competitor(item, _down)
    assert v["accepted"] is False and v["pending"] is True
    r = validator.validate_competitor(item, lambda q, a, b: [object()] * 4)
    assert r["accepted"] is False and not r.get("pending")


def test_apply_plan_stores_a_pending_row_as_pending_validation_not_needs_review(db, monkeypatch):
    monkeypatch.setattr(service, "_refresh_matcher_and_rematch", lambda *a, **k: None)
    c, e = _client_with_entity(db)
    plan = {"website": {}, "executives": [
        {"name": "Down Person", "role": "CFO", "rank": 100, "selected": False, "aliases": [],
         "validation": {"accepted": False, "pending": True, "reason": "pending validation (source unavailable): x", "sources": ["https://a.com"], "pair_count_24m": 0}},
        {"name": "Zero Person", "role": "CTO", "rank": 101, "selected": False, "aliases": [],
         "validation": {"accepted": False, "reason": "no Google News item", "sources": ["https://a.com"], "pair_count_24m": 0}},
    ], "competitors": []}
    out = service.apply_plan(db, c.id, plan, rematch=False)
    rows = {r.name: r.status for r in db.query(SeededEntity).all()}
    assert rows == {"Down Person": "pending_validation", "Zero Person": "needs_review"}
    assert out["pending_validation"] == 1 and out["needs_review"] == 1


# ------------------------------------------------------------------ 3. one limiter and breaker for Google News
class _FakeRedis:
    def __init__(self):
        self.d = {}

    def exists(self, k):
        return k in self.d

    def set(self, k, v, nx=False, px=None, ex=None):
        if nx and k in self.d:
            return None
        if px is not None:                      # a pacing slot that has already expired by the next call
            return True
        self.d[k] = v
        return True

    def incr(self, k):
        self.d[k] = int(self.d.get(k, 0)) + 1
        return self.d[k]

    def expire(self, k, s):
        return True

    def delete(self, k):
        self.d.pop(k, None)


def test_breaker_opens_after_three_failures_and_then_no_request_is_sent(monkeypatch):
    fr = _FakeRedis()
    monkeypatch.setattr(fetchers, "_gn_redis", lambda: fr)
    monkeypatch.setattr(fetchers, "GN_MIN_INTERVAL_SECONDS", 0.0)
    sent = {"n": 0}

    class Boom:
        def fetch(self, url):
            sent["n"] += 1
            raise Exception("HTTP Error 503 fetching feed")
    monkeypatch.setattr("app.adapters.rss.RSSAdapter", Boom)
    for _ in range(3):
        with pytest.raises(Exception, match="503"):
            fetchers.fetch_google_news("q", dt.date(2026, 1, 1), dt.date(2026, 2, 1), {})
    assert sent["n"] == 3 and fr.exists(fetchers._GN_CIRCUIT_KEY)
    with pytest.raises(fetchers.QuotaPaused, match="Google News"):
        fetchers.fetch_google_news("q", dt.date(2026, 1, 1), dt.date(2026, 2, 1), {})
    assert sent["n"] == 3                                                          # nothing was sent while open


def test_a_success_resets_the_failure_streak(monkeypatch):
    fr = _FakeRedis()
    monkeypatch.setattr(fetchers, "_gn_redis", lambda: fr)
    monkeypatch.setattr(fetchers, "GN_MIN_INTERVAL_SECONDS", 0.0)
    outcomes = iter([False, False, True, False, False])

    class Maybe:
        def fetch(self, url):
            if not next(outcomes):
                raise Exception("503")
            return []
    monkeypatch.setattr("app.adapters.rss.RSSAdapter", Maybe)
    for _ in range(5):
        try:
            fetchers.fetch_google_news("q", dt.date(2026, 1, 1), dt.date(2026, 2, 1), {})
        except Exception:
            pass
    assert not fr.exists(fetchers._GN_CIRCUIT_KEY)


def test_spacing_uses_one_global_slot_key(monkeypatch):
    fr = _FakeRedis()
    monkeypatch.setattr(fetchers, "_gn_redis", lambda: fr)
    monkeypatch.setattr(fetchers, "GN_MIN_INTERVAL_SECONDS", 0.0)
    waits = []
    monkeypatch.setattr(fetchers.time, "sleep", lambda s: waits.append(s))
    fr.d[fetchers._GN_SLOT_KEY] = "1"                                               # another process just made a request
    calls = {"n": 0}
    real_set = fr.set

    def set_then_free(k, v, nx=False, px=None, ex=None):
        calls["n"] += 1
        if calls["n"] == 3:
            fr.d.pop(fetchers._GN_SLOT_KEY, None)
        return real_set(k, v, nx=nx, px=px, ex=ex)
    fr.set = set_then_free
    fetchers._gn_before_request()
    assert calls["n"] == 3 and len(waits) == 2                                      # it waited its turn instead of firing
