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
from app.models.document import Document, DocumentMatch
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


# ------------------------------------------------------------------ 4. channels not collected (run log_tail, super admin only)
class _HashRedis(_FakeRedis):
    def __init__(self):
        super().__init__()
        self.h = {}

    def hset(self, key, field, value):
        self.h.setdefault(key, {})[field] = value

    def hgetall(self, key):
        return dict(self.h.get(key, {}))

    def get(self, k):
        return self.d.get(k)


@pytest.fixture()
def hredis(monkeypatch):
    from app.utils import redis_client as rc
    fr = _HashRedis()
    monkeypatch.setattr(rc.redis_client, "client", fr, raising=False)
    return fr


def test_channel_notes_become_one_line_with_reasons_and_nothing_when_all_collected(hredis):
    assert aggregation_tasks._channels_line("r1") == ""
    aggregation_tasks._note_channel("r1", "instagram", "token invalid")
    aggregation_tasks._note_channel("r1", "reddit", "token invalid")
    aggregation_tasks._note_channel("r1", "google_news", "fetch failed: HTTP Error 503")
    line = aggregation_tasks._channels_line("r1")
    assert line.startswith(" | Channels not collected: ")
    assert "Instagram (token invalid)" in line and "Reddit (token invalid)" in line and "Google News (fetch failed: HTTP Error 503)" in line
    assert aggregation_tasks._channels_line("other-run") == ""


def test_only_super_admin_sees_the_channels_part_of_log_tail():
    from types import SimpleNamespace
    from app.api.endpoints.clients import _visible_log_tail
    from app.models.user import ROLE_SUPER_ADMIN
    text = "Pipeline completed" + aggregation_tasks.CHANNELS_MARKER + "Instagram (token invalid)"
    assert _visible_log_tail(text, SimpleNamespace(role=ROLE_SUPER_ADMIN)) == text
    assert _visible_log_tail(text, SimpleNamespace(role="client")) == "Pipeline completed"
    assert _visible_log_tail(None, SimpleNamespace(role="client")) is None
    assert _visible_log_tail("Pipeline completed", SimpleNamespace(role="client")) == "Pipeline completed"


def test_apify_token_status_missing_invalid_ok_and_unknown(hredis, monkeypatch):
    import urllib.request
    import urllib.error
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    assert aggregation_tasks._apify_token_status() == (False, "token missing")
    monkeypatch.setenv("APIFY_API_TOKEN", "x")

    def deny(*a, **k):
        raise urllib.error.HTTPError("u", 401, "no", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    assert aggregation_tasks._apify_token_status() == (False, "token invalid")
    assert hredis.d["apify:token_status"] == "token invalid"                      # cached: the next run makes no call
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must use the cache")))
    assert aggregation_tasks._apify_token_status() == (False, "token invalid")
    hredis.d.clear()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: object())
    assert aggregation_tasks._apify_token_status() == (True, "")
    hredis.d.clear()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("dns")))
    assert aggregation_tasks._apify_token_status() == (True, "")                  # unknown: let the real call try, cache nothing
    assert "apify:token_status" not in hredis.d


def test_feed_channel_names():
    assert aggregation_tasks._feed_channel("https://news.google.com/rss/search?q=x") == "google_news"
    assert aggregation_tasks._feed_channel("https://api.gdeltproject.org/api/v2/doc/doc?q=x") == "gdelt"
    assert aggregation_tasks._feed_channel("https://hn.algolia.com/api/v1/search?query=x") == "hn"


# ------------------------------------------------------------------ 6. deleting a client never removes another client's documents or sources
def test_delete_client_keeps_documents_and_sources_another_client_still_uses(db, monkeypatch):
    from app.models.rss_feed import RSSFeed
    from app.models.source import Source
    from app.services import client_service

    class _R:
        def delete(self, *a, **k):
            return 0
    import app.utils.redis_client as rc
    monkeypatch.setattr(rc, "redis_client", _R())

    a, ea = _client_with_entity(db)
    b, eb = _client_with_entity(db)
    s1 = Source(id=uuid.uuid4(), name="only A", source_type="rss", schedule_cron="x", url="https://f/one")
    s2 = Source(id=uuid.uuid4(), name="shared", source_type="rss", schedule_cron="x", url="https://f/shared")
    s3 = Source(id=uuid.uuid4(), name="history", source_type="rss", schedule_cron="x", url="https://f/history")
    db.add_all([s1, s2, s3])
    db.add_all([RSSFeed(id=uuid.uuid4(), feed_name="a1", feed_url=s1.url, client_id=a.id),
                RSSFeed(id=uuid.uuid4(), feed_name="a2", feed_url=s2.url, client_id=a.id),
                RSSFeed(id=uuid.uuid4(), feed_name="b2", feed_url=s2.url, client_id=b.id)])
    db.flush()

    def doc(src):
        d = Document(id=uuid.uuid4(), url=f"https://x.com/{uuid.uuid4()}", content_hash=uuid.uuid4().hex, normalized_content="x", source_id=src.id)
        db.add(d)
        db.flush()
        return d

    only_a, also_b, in_shared = doc(s1), doc(s1), doc(s2)
    match_only_a, match_both = doc(s3), doc(s3)   # in a source no feed of A owns, linked through document_matches only
    db.add_all([DocumentMatch(id=uuid.uuid4(), document_id=match_only_a.id, matched_entity_id=ea.id),
                DocumentMatch(id=uuid.uuid4(), document_id=match_both.id, matched_entity_id=ea.id),
                DocumentMatch(id=uuid.uuid4(), document_id=match_both.id, matched_entity_id=eb.id)])
    match_only_a_id, match_both_id = match_only_a.id, match_both.id
    only_a_id, also_b_id, in_shared_id, s1_id, s2_id, a_id, eb_id = only_a.id, also_b.id, in_shared.id, s1.id, s2.id, a.id, eb.id
    for d, e in ((only_a, ea), (also_b, ea), (also_b, eb), (in_shared, eb)):
        db.add(EntityMention(id=uuid.uuid4(), document_id=d.id, entity_id=e.id, mention_count=1))
    db.commit()

    client_service.delete_client(db, a_id)
    db.expire_all()

    assert db.query(Client).filter(Client.id == a_id).first() is None
    assert db.query(Document).filter(Document.id == only_a_id).first() is None          # only A's: deleted
    assert db.query(Document).filter(Document.id == also_b_id).first() is not None      # B's entity also mentions it: kept
    assert db.query(Document).filter(Document.id == in_shared_id).first() is not None   # source shared with B's feed: kept
    assert db.query(Document).filter(Document.id == match_only_a_id).first() is None    # matched only to A (no mention row): deleted, not orphaned
    assert db.query(Document).filter(Document.id == match_both_id).first() is not None   # matched by B too: kept
    assert db.query(Source).filter(Source.id == s1_id).first() is not None              # still referenced by the kept document
    assert db.query(Source).filter(Source.id == s2_id).first() is not None              # B still has a feed on it
    assert db.query(EntityMention).filter(EntityMention.entity_id == eb_id).count() == 2  # B's data untouched
