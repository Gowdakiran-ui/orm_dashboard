"""Historical backfill: slice splitting, idempotent re-run, dry run, YouTube date fallback, no-recurring-schedule."""
import os
import sys
import uuid
import datetime as dt

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity
from app.models.backfill import BackfillSlice
from app.services.backfill import slicing
from app.services.backfill.engine import BackfillConfig, dry_run, plan_slices, run_client
from app.services.backfill.queries import build_queries


@compiles(PG_UUID, 'sqlite')
def _uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, 'sqlite')
def _jsonb(element, compiler, **kw):
    return "TEXT"


_engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(_engine)
Session = sessionmaker(bind=_engine)

BRAND_Q = '"Acme Corp"'


def _client(db, execs=("Jane Doe",), with_competitor=False):
    c = Client(id=uuid.uuid4(), name=f"Acme-{uuid.uuid4()}")
    db.add(c)
    db.flush()
    db.add(Entity(id=uuid.uuid4(), client_id=c.id, name="Acme Corp", entity_type="brand"))
    for n in execs:
        db.add(Entity(id=uuid.uuid4(), client_id=c.id, name=n, entity_type="person"))
    if with_competitor:
        db.add(Entity(id=uuid.uuid4(), client_id=c.id, name="Rival Ltd", entity_type="competitor"))
    db.commit()
    return c


def _fake_ingest(db, client_id, src, raw, **kw):
    return {"seen": len(raw), "saved": len(raw), "deduped": 0, "skipped_undated": 0, "skipped_future": 0, "failed": 0}


# ---------------------------------------------------------------- slicing
def test_calendar_slices_monthly_cover_range_without_gaps():
    s = slicing.calendar_slices(dt.date(2015, 1, 1), dt.date(2015, 4, 10), 1)
    assert s[0] == (dt.date(2015, 1, 1), dt.date(2015, 2, 1))
    assert s[-1] == (dt.date(2015, 4, 1), dt.date(2015, 4, 10))
    assert all(a[1] == b[0] for a, b in zip(s, s[1:]))


def test_split_slice_halves_until_single_day():
    s = (dt.date(2020, 1, 1), dt.date(2020, 2, 1))
    a, b = slicing.split_slice(s)
    assert a[0] == s[0] and b[1] == s[1] and a[1] == b[0]
    assert slicing.split_slice((dt.date(2020, 1, 1), dt.date(2020, 1, 2))) is None


def test_needs_split_only_at_or_over_cap():
    assert slicing.needs_split(90, 90) and slicing.needs_split(100, 90)
    assert not slicing.needs_split(89, 90)


# ------------------------------------------------------------------ queries
def test_competitors_and_products_are_off_by_default():
    db = Session()
    c = _client(db, with_competitor=True)
    assert {q.kind for q in build_queries(db, c.id)} == {"brand", "risk", "executive"}
    assert "competitor" in {q.kind for q in build_queries(db, c.id, include_competitors=True)}


def test_executive_query_is_paired_with_brand():
    db = Session()
    c = _client(db)
    ex = next(q for q in build_queries(db, c.id) if q.kind == "executive")
    assert '"Jane Doe"' in ex.google_news and '"Acme Corp"' in ex.google_news


# ----------------------------------------- slice splitting at the cap + resume
def test_slice_at_cap_is_split_and_children_are_fetched_under_cap():
    db = Session()
    c = _client(db, execs=())
    cfg = BackfillConfig(start=dt.date(2020, 1, 1), end=dt.date(2020, 2, 1), sources=("google_news",), max_slices_per_run=200)

    def fake_gn(query, s, e, ctx):
        # a full month is truncated at the cap; any smaller window is under it
        return [{}] * (95 if (e - s).days >= 30 else 5)

    run_client(db, c.id, cfg, fetchers={"google_news": fake_gn}, ingest=_fake_ingest)
    rows = db.query(BackfillSlice).filter(BackfillSlice.client_id == c.id, BackfillSlice.query == BRAND_Q).all()
    statuses = [r.status for r in rows]
    assert "SPLIT" in statuses and statuses.count("DONE") >= 2
    assert db.query(BackfillSlice).filter(BackfillSlice.client_id == c.id, BackfillSlice.status == "PENDING").count() == 0


def test_rerun_is_idempotent_and_never_refetches_finished_slices():
    db = Session()
    c = _client(db)
    cfg = BackfillConfig(start=dt.date(2021, 1, 1), end=dt.date(2021, 7, 1), sources=("google_news",), max_slices_per_run=500)
    calls = []

    def fake_gn(query, s, e, ctx):
        calls.append((query, s, e))
        return [{}] * 3

    first = run_client(db, c.id, cfg, fetchers={"google_news": fake_gn}, ingest=_fake_ingest)
    n_first = len(calls)
    n_rows = db.query(BackfillSlice).filter(BackfillSlice.client_id == c.id).count()
    assert n_first > 0 and first["remaining"] == 0

    second = run_client(db, c.id, cfg, fetchers={"google_news": fake_gn}, ingest=_fake_ingest)
    assert len(calls) == n_first                  # nothing refetched
    assert second["seeded"] == 0 and second["processed"] == 0
    assert db.query(BackfillSlice).filter(BackfillSlice.client_id == c.id).count() == n_rows


def test_failed_slice_is_retried_on_resume_and_finished_ones_are_not():
    db = Session()
    c = _client(db, execs=())
    cfg = BackfillConfig(start=dt.date(2022, 1, 1), end=dt.date(2022, 5, 1), sources=("google_news",),
                         max_slices_per_run=500, max_attempts=5)

    def flaky(query, s, e, ctx):
        if s == dt.date(2022, 3, 1) and query == BRAND_Q:
            raise RuntimeError("boom")
        return []

    run_client(db, c.id, cfg, fetchers={"google_news": flaky}, ingest=_fake_ingest)
    bad = db.query(BackfillSlice).filter(BackfillSlice.client_id == c.id, BackfillSlice.status == "PENDING").all()
    assert len(bad) >= 1 and all(b.error for b in bad)

    refetched = []
    run_client(db, c.id, cfg, fetchers={"google_news": lambda q, s, e, ctx: refetched.append((q, s)) or []}, ingest=_fake_ingest)
    assert refetched and all(s == dt.date(2022, 3, 1) and q == BRAND_Q for q, s in refetched)


# ------------------------------------------------------------------ dry run
def test_dry_run_writes_nothing_and_makes_no_paid_calls():
    db = Session()
    c = _client(db)
    before = db.query(BackfillSlice).count()
    report = dry_run(db, c.id, BackfillConfig(start=dt.date(2024, 1, 1), end=dt.date(2025, 1, 1)))
    assert db.query(BackfillSlice).count() == before
    assert report["db_writes"] == 0 and report["paid_calls"] == 0
    assert report["planned_slices"] > 0 and report["slices_to_fetch"] == report["planned_slices"]


def test_gdelt_is_only_planned_inside_its_90_day_window():
    db = Session()
    c = _client(db, execs=())
    end = dt.date(2026, 10, 17)
    cfg = BackfillConfig(start=dt.date(2015, 1, 1), end=end, sources=("gdelt",))
    plan = plan_slices(build_queries(db, c.id), cfg)
    assert plan and min(p.start for p in plan) >= end - dt.timedelta(days=90)


# ------------------------------------------- YouTube: no silent "now" date
def test_youtube_unparseable_date_is_not_defaulted_to_now():
    from app.adapters.youtube import YouTubeAdapter
    a = YouTubeAdapter()
    base = {"id": {"videoId": "abc"}, "snippet": {"title": "t", "description": "d", "channelTitle": "c"}}
    bad = a.normalize({**base, "snippet": {**base["snippet"], "publishedAt": "not-a-date"}}, str(uuid.uuid4()))
    missing = a.normalize(base, str(uuid.uuid4()))
    ok = a.normalize({**base, "snippet": {**base["snippet"], "publishedAt": "2019-03-04T05:06:07Z"}}, str(uuid.uuid4()))
    assert bad["published_at"] is None and missing["published_at"] is None
    assert ok["published_at"] == dt.datetime(2019, 3, 4, 5, 6, 7, tzinfo=dt.timezone.utc)


def test_ingest_skips_undated_items(monkeypatch):
    from app.services.backfill import engine
    from app.services.backfill.fetchers import SOURCES
    import app.services.document_service as ds
    db = Session()
    c = _client(db)
    saved = []
    monkeypatch.setattr(ds, "process_and_save_document", lambda db_, d: (saved.append(d) or (True, False, 0)))
    raw_bad = {"id": {"videoId": "x"}, "snippet": {"title": "t", "description": "d", "publishedAt": "garbage"}}
    raw_ok = {"id": {"videoId": "y"}, "snippet": {"title": "t", "description": "d", "publishedAt": "2020-01-02T03:04:05Z"}}
    st = engine.ingest_items(db, c.id, SOURCES["youtube"], [raw_bad, raw_ok])
    assert st["skipped_undated"] == 1 and st["saved"] == 1 and len(saved) == 1
    assert saved[0].published_at.year == 2020


# ------------------------------------------ no recurring collection is added
def test_backfill_tasks_are_not_in_any_beat_schedule():
    from app.core.celery_app import celery_app
    scheduled = {v["task"] for v in celery_app.conf.beat_schedule.values()}
    assert not any("backfill" in t for t in scheduled)


def test_run_pipeline_never_references_backfill():
    path = os.path.join(os.path.dirname(__file__), "..", "app", "workers", "aggregation_tasks.py")
    assert "backfill" not in open(path, encoding="utf8").read().lower()


# ------------------------------------------------------ onboarding hook
class _FakeRedisInner:
    def __init__(self):
        self.keys = set()

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True


class _FakeRedis:
    def __init__(self):
        self.client = _FakeRedisInner()


def test_onboarding_endpoint_enqueues_backfill_exactly_once(monkeypatch):
    import types
    import app.api.endpoints.clients as clients_ep
    import app.utils.redis_client as rc
    from app.core.celery_app import celery_app

    fake_redis = _FakeRedis()
    monkeypatch.setattr(rc, "redis_client", fake_redis)
    sent = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, **kw: sent.append({"name": name, **kw}))
    monkeypatch.delenv("BACKFILL_ON_ONBOARD", raising=False)

    cid = uuid.uuid4()
    monkeypatch.setattr(clients_ep, "onboard_client", lambda db, data: types.SimpleNamespace(id=cid))

    class _DB:
        def add(self, *_): pass
        def commit(self): pass

    user = types.SimpleNamespace(id=uuid.uuid4())
    clients_ep.onboard_new_client(types.SimpleNamespace(), db=_DB(), current_user=user)
    assert len(sent) == 1 and sent[0]["args"][0] == str(cid)

    # a second enqueue attempt for the same client (retry, double click) is a no-op
    from app.services.backfill.enqueue import enqueue_client_backfill
    assert enqueue_client_backfill(cid) is False
    assert len(sent) == 1


def test_onboarding_survives_a_broker_failure(monkeypatch):
    import app.utils.redis_client as rc
    from app.core.celery_app import celery_app
    from app.services.backfill.enqueue import enqueue_client_backfill
    monkeypatch.setattr(rc, "redis_client", _FakeRedis())

    def boom(name, **kw):
        raise ConnectionError("broker down")

    monkeypatch.setattr(celery_app, "send_task", boom)
    assert enqueue_client_backfill(uuid.uuid4()) is False     # no exception


def test_backfill_on_onboard_can_be_switched_off(monkeypatch):
    import app.utils.redis_client as rc
    from app.core.celery_app import celery_app
    from app.services.backfill.enqueue import enqueue_client_backfill
    monkeypatch.setattr(rc, "redis_client", _FakeRedis())
    sent = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, **kw: sent.append({"name": name, **kw}))
    monkeypatch.setenv("BACKFILL_ON_ONBOARD", "false")
    assert enqueue_client_backfill(uuid.uuid4()) is False and not sent
