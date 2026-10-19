"""
Bounded onboarding backfill: relevance filter, query/slice priority, processing cap + resume,
skipped slices, YouTube start year, stop switch, single NLP drain chain.
"""
import os
import sys
import uuid
import datetime as dt

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityAlias, EntityKeyword
from app.models.document import Document
from app.models.source import Source, SourceCategory
from app.models.backfill import BackfillSlice
from app.services.backfill import control, processing
from app.services.backfill.engine import BackfillConfig, ingest_items, plan_slices, run_client
from app.services.backfill.fetchers import SOURCES
from app.services.backfill.queries import build_queries
from app.services.backfill.relevance import has_risk_term, is_relevant, tracked_terms


@compiles(PG_UUID, 'sqlite')
def _uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, 'sqlite')
def _jsonb(element, compiler, **kw):
    return "TEXT"


_engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(_engine)
Session = sessionmaker(bind=_engine)

NOW = dt.datetime.now(dt.timezone.utc)


@pytest.fixture(autouse=True)
def _no_real_redis(monkeypatch):
    """The stop switch reads Redis; keep unit tests independent of a running Redis."""
    flag = {"on": False}
    monkeypatch.setattr(control, "is_stopped", lambda: flag["on"])
    monkeypatch.setattr(control, "set_stopped", lambda: flag.update(on=True))
    monkeypatch.setattr(control, "clear_stopped", lambda: flag.update(on=False))
    co = {"on": False}
    monkeypatch.setattr(control, "is_collect_only", lambda: co["on"])
    monkeypatch.setattr(control, "set_collect_only", lambda: co.update(on=True))
    monkeypatch.setattr(control, "clear_collect_only", lambda: co.update(on=False))
    return flag


def _client(db, execs=("Jane Doe",)):
    c = Client(id=uuid.uuid4(), name=f"Acme-{uuid.uuid4()}")
    db.add(c)
    db.flush()
    brand = Entity(id=uuid.uuid4(), client_id=c.id, name="Acme Corp", entity_type="brand")
    db.add(brand)
    for n in execs:
        db.add(Entity(id=uuid.uuid4(), client_id=c.id, name=n, entity_type="person"))
    db.add(Entity(id=uuid.uuid4(), client_id=c.id, name="Rival Ltd", entity_type="competitor"))
    db.flush()
    db.add(EntityAlias(entity_id=brand.id, alias_text="AcmeCo"))
    db.add(EntityKeyword(entity_id=brand.id, keyword_text="Acme Corp bankruptcy", category="RISK"))
    db.add(EntityKeyword(entity_id=brand.id, keyword_text="Acme", category="ALIAS"))
    db.commit()
    return c


# ----------------------------------------------------------- relevance filter
def test_tracked_terms_include_brand_people_aliases_not_risk_or_competitors():
    db = Session()
    c = _client(db)
    terms = {t.strip() for t in tracked_terms(db, c.id)}
    assert {"acme corp", "jane doe", "acmeco", "acme"} <= terms
    assert not any("bankruptcy" in t for t in terms)       # RISK keyword rows are generic phrases
    assert "rival ltd" not in terms                        # competitors only behind the flag
    assert "rival ltd" in {t.strip() for t in tracked_terms(db, c.id, include_competitors=True)}


def test_is_relevant_matches_whole_words_in_title_or_summary():
    terms = [" acme corp ", " jane doe "]
    assert is_relevant("Acme Corp's Q3 results", "", terms)
    assert is_relevant("Quarterly roundup", "CEO Jane Doe said ...", terms)
    assert not is_relevant("Tata Sons board row", "Noel Tata and Venu Srinivasan", terms)
    assert not is_relevant("Acmecorporation news", "", terms)      # not a whole-word match


def test_ingest_drops_irrelevant_items_before_saving_and_counts_them(monkeypatch):
    import app.services.document_service as ds
    db = Session()
    c = _client(db)
    saved = []
    monkeypatch.setattr(ds, "process_and_save_document", lambda db_, d: (saved.append(d) or (True, False, 0)))
    pub = "2022-05-01T00:00:00Z"
    good = {"id": {"videoId": "g"}, "snippet": {"title": "Acme Corp recall", "description": "d", "publishedAt": pub}}
    bad = {"id": {"videoId": "b"}, "snippet": {"title": "Unrelated cooking video", "description": "d", "publishedAt": pub}}
    terms = tracked_terms(db, c.id)
    st = ingest_items(db, c.id, SOURCES["youtube"], [good, bad], terms=terms)
    assert st["dropped_irrelevant"] == 1 and st["saved"] == 1 and len(saved) == 1
    assert saved[0].title == "Acme Corp recall"
    # without terms nothing is dropped (filter off)
    saved.clear()
    st2 = ingest_items(db, c.id, SOURCES["youtube"], [good, bad])
    assert st2["dropped_irrelevant"] == 0 and len(saved) == 2


# ------------------------------------------------------------ slice priority
def test_slices_run_brand_and_risk_first_then_people_and_newest_first():
    db = Session()
    c = _client(db)
    cfg = BackfillConfig(start=dt.date(2020, 1, 1), end=dt.date(2021, 1, 1), sources=("google_news",), max_slices_per_run=500)
    order = []

    def fake_gn(query, s, e, ctx):
        order.append((query, s))
        return []

    run_client(db, c.id, cfg, fetchers={"google_news": fake_gn}, ingest=lambda *a, **k: {"saved": 0})
    kinds = []
    for q, _s in order:
        kinds.append("executive" if '"Jane Doe"' in q else "risk" if "(" in q else "brand")
    first_exec = kinds.index("executive")
    assert set(kinds[:first_exec]) <= {"brand", "risk"} and "executive" not in kinds[:first_exec]
    assert all(k == "executive" for k in kinds[first_exec:])
    brand_starts = [s for (q, s), k in zip(order, kinds) if k == "brand"]
    assert brand_starts == sorted(brand_starts, reverse=True)       # newest first


def test_competitors_stay_off_and_run_last_when_enabled():
    db = Session()
    c = _client(db)
    cfg = BackfillConfig(start=dt.date(2020, 1, 1), end=dt.date(2020, 4, 1), sources=("google_news",), max_slices_per_run=500)
    assert not any("Rival" in q for q in (p.query for p in plan_slices(build_queries(db, c.id), cfg)))
    cfg2 = BackfillConfig(start=cfg.start, end=cfg.end, sources=("google_news",), include_competitors=True, max_slices_per_run=500)
    order = []
    run_client(db, c.id, cfg2, fetchers={"google_news": lambda q, s, e, ctx: order.append(q) or []},
               ingest=lambda *a, **k: {"saved": 0})
    assert "Rival" in order[-1]


# ------------------------------------------------------------ skipped slices
def test_skipped_slices_are_never_refetched_or_reseeded():
    db = Session()
    c = _client(db, execs=())
    cfg = BackfillConfig(start=dt.date(2021, 1, 1), end=dt.date(2021, 4, 1), sources=("google_news",), max_slices_per_run=500)
    calls = []
    run_client(db, c.id, cfg, fetchers={"google_news": lambda q, s, e, ctx: calls.append((q, s)) or []},
               ingest=lambda *a, **k: {"saved": 0})
    # operator skips whatever is still PENDING for this client (here: re-open one slice, then skip it)
    row = db.query(BackfillSlice).filter(BackfillSlice.client_id == c.id).first()
    row.status = "PENDING"
    db.commit()
    db.query(BackfillSlice).filter(BackfillSlice.client_id == c.id, BackfillSlice.status == "PENDING").update(
        {"status": "SKIPPED"}, synchronize_session=False)
    db.commit()
    n_before = len(calls)
    summary = run_client(db, c.id, cfg, fetchers={"google_news": lambda q, s, e, ctx: calls.append((q, s)) or []},
                         ingest=lambda *a, **k: {"saved": 0})
    assert len(calls) == n_before and summary["processed"] == 0 and summary["seeded"] == 0
    assert db.query(BackfillSlice).filter(BackfillSlice.status == "SKIPPED", BackfillSlice.client_id == c.id).count() == 1


# ------------------------------------------------------------ YouTube start year
def test_youtube_slices_start_at_the_configured_year_google_news_keeps_2015():
    db = Session()
    c = _client(db, execs=())
    cfg = BackfillConfig(start=dt.date(2015, 1, 1), end=dt.date(2026, 10, 19), sources=("google_news", "youtube"))
    plan = plan_slices(build_queries(db, c.id), cfg)
    yt = [p for p in plan if p.source == "youtube"]
    gn = [p for p in plan if p.source == "google_news"]
    assert min(p.start for p in yt) == dt.date(2022, 1, 1)
    assert min(p.start for p in gn) == dt.date(2015, 1, 1)
    cfg2 = BackfillConfig(start=cfg.start, end=cfg.end, sources=("youtube",), youtube_start_year=2024)
    assert min(p.start for p in plan_slices(build_queries(db, c.id), cfg2)) == dt.date(2024, 1, 1)


# ------------------------------------------------- processing cap, order, resume
def _backfill_docs(db, c, n_risk=3, n_plain=7):
    cat = SourceCategory(name=f"cat-{uuid.uuid4()}", base_reliability_score=1.0)
    db.add(cat)
    db.flush()
    src = Source(category_id=cat.id, name="GN history", source_type="rss", url=f"backfill://{c.id}/google_news",
                 schedule_cron="on-demand", is_active=False)
    db.add(src)
    db.flush()
    ids = {"risk": [], "plain": []}
    for i in range(n_plain):      # plain docs, newer ones have a higher i
        d = Document(id=uuid.uuid4(), url=f"http://x.test/p{uuid.uuid4()}", normalized_content="quarterly results", title=f"Acme news {i}",
                     source_id=src.id, published_at=NOW - dt.timedelta(days=100 - i), processing_status="PENDING")
        db.add(d)
        ids["plain"].append(d.id)
    for i in range(n_risk):       # OLD documents, but they carry a risk keyword
        d = Document(id=uuid.uuid4(), url=f"http://x.test/r{uuid.uuid4()}", normalized_content="RERA complaint filed", title=f"Acme dispute {i}",
                     source_id=src.id, published_at=NOW - dt.timedelta(days=3000 + i), processing_status="PENDING")
        db.add(d)
        ids["risk"].append(d.id)
    db.commit()
    return ids


def test_risk_keyword_docs_go_first_then_newest_first():
    db = Session()
    c = _client(db)
    ids = _backfill_docs(db, c)
    batch = [r[0] for r in processing.next_batch(db, c.id, 10)]
    assert set(batch[:3]) == set(ids["risk"])                          # old risk docs ahead of every plain doc
    assert batch[3:] == list(reversed(ids["plain"]))                   # then newest first
    assert has_risk_term("Acme dispute", "") is False and has_risk_term("x", "RERA order") is True


def test_processing_stops_at_the_cap_and_continue_command_resumes():
    db = Session()
    c = _client(db)
    ids = _backfill_docs(db, c, n_risk=3, n_plain=7)       # 10 docs
    sent = []
    send = lambda doc_id, client_id: sent.append(doc_id)

    r1 = processing.dispatch(db, c.id, 100, cap=4, send=send)
    assert r1["dispatched"] == 4 and r1["pending_left"] == 6
    assert set(sent[:3]) == {str(i) for i in ids["risk"]}              # risk docs first

    r2 = processing.dispatch(db, c.id, 100, cap=4, send=send)           # cap reached: nothing more
    assert r2["dispatched"] == 0 and r2["cap_remaining"] == 0 and len(sent) == 4

    # `--continue-processing` ignores the cap and hands over the next batch on request
    r3 = processing.dispatch(db, c.id, 5, respect_cap=False, send=send)
    assert r3["dispatched"] == 5 and r3["pending_left"] == 1 and len(sent) == 9
    assert len(set(sent)) == 9                                         # no document handed over twice
    assert processing.processed_count(db, c.id) == 9


def test_default_cap_is_500_and_onboarding_defaults():
    from app.services.backfill import settings as s
    assert s.MAX_PROCESS_DOCS_PER_CLIENT == 500 and s.YOUTUBE_START_YEAR == 2022 and s.RELEVANCE_FILTER_DEFAULT is True
    cfg = BackfillConfig()
    assert cfg.include_competitors is False and cfg.include_products is False and cfg.start == dt.date(2015, 1, 1)


# ------------------------------------------------------------ stop switch
def test_stop_switch_halts_the_slice_loop(_no_real_redis):
    db = Session()
    c = _client(db)
    cfg = BackfillConfig(start=dt.date(2021, 1, 1), end=dt.date(2021, 7, 1), sources=("google_news",), max_slices_per_run=500)
    calls = []

    def fake_gn(q, s, e, ctx):
        calls.append(s)
        if len(calls) == 3:
            control.set_stopped()          # operator hits the switch mid-run
        return []

    summary = run_client(db, c.id, cfg, fetchers={"google_news": fake_gn}, ingest=lambda *a, **k: {"saved": 0})
    assert summary["stopped"] is True and len(calls) == 3 and summary["remaining"] > 0


def test_drain_runs_one_chain_and_ends_when_everything_capped_in_is_handed_over(monkeypatch, _no_real_redis):
    import app.workers.backfill_tasks as bt
    import app.utils.redis_client as rc

    store = {}

    class _Inner:
        def set(self, k, v, nx=False, ex=None):
            if nx and k in store:
                return None
            store[k] = v
            return True

        def llen(self, q):
            return 0

        def delete(self, k):
            store.pop(k, None)

    class _R:
        client = _Inner()
        def get(self, k):
            return store.get(k)
        def delete(self, k):
            store.pop(k, None)

    monkeypatch.setattr(rc, "redis_client", _R())
    sent_tasks = []
    monkeypatch.setattr(bt, "_send", lambda name, **kw: sent_tasks.append((name, kw)))

    # one chain at a time
    assert bt.start_drain() is True
    assert bt.start_drain() is False
    assert len([t for t in sent_tasks if t[0].endswith("drain_backfill_nlp")]) == 1

    # a second chain with a different id is superseded and does not reschedule itself
    sent_tasks.clear()
    out = bt.drain_backfill_nlp.run(tick=3, chain="not-the-owner")
    assert out["status"] == "superseded" and not sent_tasks

    # stop switch ends the chain and frees the slot
    control.set_stopped()
    out = bt.drain_backfill_nlp.run(tick=0, chain=store[bt.DRAIN_CHAIN_KEY])
    assert out["status"] == "stopped" and bt.DRAIN_CHAIN_KEY not in store


def test_collect_only_flag_blocks_feeder_start_and_ends_a_running_chain(monkeypatch):
    import app.workers.backfill_tasks as bt
    import app.utils.redis_client as rc

    store = {}

    class _Inner:
        def set(self, k, v, nx=False, ex=None):
            if nx and k in store:
                return None
            store[k] = v
            return True

        def llen(self, q):
            return 0

    class _R:
        client = _Inner()
        def get(self, k):
            return store.get(k)
        def delete(self, k):
            store.pop(k, None)

    monkeypatch.setattr(rc, "redis_client", _R())
    sent = []
    monkeypatch.setattr(bt, "_send", lambda name, **kw: sent.append(name))

    control.set_collect_only()
    assert bt.start_drain() is False and not sent and bt.DRAIN_CHAIN_KEY not in store

    control.clear_collect_only()
    assert bt.start_drain() is True
    control.set_collect_only()                     # flag flipped while a chain is alive
    out = bt.drain_backfill_nlp.run(tick=1, chain=store[bt.DRAIN_CHAIN_KEY])
    assert out["status"] == "collect_only" and bt.DRAIN_CHAIN_KEY not in store
    assert not [n for n in sent[1:] if n.endswith("drain_backfill_nlp")]   # no reschedule
