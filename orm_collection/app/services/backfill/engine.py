"""
One-time historical backfill engine.

Separate from Run Pipeline: nothing in aggregation_tasks.py calls this, and it
adds no Celery beat entry. It is entered from backfill_tasks.run_client_backfill
(Celery), scripts/run_backfill.py (CLI) or the one-time onboarding enqueue.

Flow per client:
  1. plan   - build queries (brand, risk-word variants, tracked executives; competitors/products
              only behind flags) x sources x date slices
  2. seed   - insert the planned slices into backfill_slices (ON CONFLICT DO NOTHING)
  3. run    - take PENDING slices newest-first, fetch, ingest through the normal
              process_and_save_document (ON CONFLICT DO NOTHING dedup + inline matching),
              mark DONE; a slice that hits its source's cap is split into halves
  4. NLP    - new documents stay PENDING under a per-client `backfill://` source (the live
              pipeline's PENDING sweep only looks at its own feed sources, so it never sees
              them); backfill_tasks.drain_backfill_nlp feeds them to the NLP queue in small
              batches, only while that queue is short.

Free sources only (Google News RSS, YouTube Data API on its own quota ceiling, GDELT DOC, HN Algolia).
"""
import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import structlog

from app.services.backfill import settings as bf_settings
from app.services.backfill import slicing
from app.services.backfill.fetchers import (
    SOURCES, SourceDef, QuotaPaused, SourceUnavailable, GDELT_WINDOW_DAYS, load_adapter,
)
from app.services.backfill.queries import QuerySpec, build_queries
from app.services.backfill.relevance import KIND_PRIORITY, SOURCE_PRIORITY, is_relevant, tracked_terms

logger = structlog.get_logger()

DEFAULT_START = dt.date(2015, 1, 1)
# Measured on production 2026-10-18/19 (backfilled docs processed per hour, steady 510-580): ~540 docs/hour
# with the 2-process NLP worker under load. The 4.6 s/doc quoted in aggregation_tasks.py comments is NOT what
# the box does for backfill traffic (observed 23-35 s per doc per process).
NLP_DOCS_PER_HOUR_MEASURED = 540

# slice width in months, by (source, query kind)
WIDTH_MONTHS: Dict[Tuple[str, str], int] = {
    ("google_news", "brand"): 1, ("google_news", "risk"): 3, ("google_news", "executive"): 12,
    ("google_news", "competitor"): 3, ("google_news", "product"): 12,
    ("youtube", "brand"): 1, ("youtube", "risk"): 12, ("youtube", "executive"): 12,
    ("youtube", "competitor"): 12, ("youtube", "product"): 12,
    ("hn", "brand"): 12, ("hn", "executive"): 12, ("hn", "competitor"): 12, ("hn", "product"): 12,
}
GDELT_SLICE_DAYS = 15


@dataclass
class BackfillConfig:
    start: dt.date = DEFAULT_START
    end: Optional[dt.date] = None                       # default: today (UTC)
    sources: Tuple[str, ...] = ("google_news", "youtube", "gdelt", "hn")
    include_competitors: bool = False                   # config flag, default OFF
    include_products: bool = False                      # config flag, default OFF
    exclude_entities: Tuple[str, ...] = ()
    youtube_units_budget: Optional[int] = bf_settings.YOUTUBE_RUN_BUDGET   # per Celery run; the daily ceiling in fetchers.py also applies
    max_slices_per_run: int = 200
    max_attempts: int = 3
    relevance_filter: bool = bf_settings.RELEVANCE_FILTER_DEFAULT   # drop items naming neither the brand nor a tracked entity
    youtube_start_year: int = bf_settings.YOUTUBE_START_YEAR         # Google News still starts at `start` (2015)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat() if self.end else None
        d["sources"] = list(self.sources)
        d["exclude_entities"] = list(self.exclude_entities)
        return d

    @staticmethod
    def from_dict(d: Optional[Dict[str, Any]]) -> "BackfillConfig":
        d = dict(d or {})
        if d.get("start"):
            d["start"] = dt.date.fromisoformat(d["start"])
        else:
            d.pop("start", None)
        d["end"] = dt.date.fromisoformat(d["end"]) if d.get("end") else None
        if "sources" in d:
            d["sources"] = tuple(d["sources"])
        if "exclude_entities" in d:
            d["exclude_entities"] = tuple(d["exclude_entities"])
        return BackfillConfig(**d)

    def effective_end(self) -> dt.date:
        return self.end or (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1))


@dataclass
class PlannedSlice:
    source: str
    kind: str
    entity_id: Optional[str]
    entity_name: str
    query: str
    start: dt.date
    end: dt.date


# ------------------------------------------------------------------- planning
def plan_slices(specs: Iterable[QuerySpec], cfg: BackfillConfig) -> List[PlannedSlice]:
    """Pure: no DB, no network."""
    end = cfg.effective_end()
    out: List[PlannedSlice] = []
    for spec in specs:
        for name in cfg.sources:
            src = SOURCES[name]
            query = getattr(spec, src.query_attr)
            if not query:
                continue
            if name == "gdelt":
                # GDELT DOC only holds ~3 months (DOCS), so only that window is ever planned.
                g_start = max(cfg.start, end - dt.timedelta(days=GDELT_WINDOW_DAYS - 1))
                for a, b in slicing.fixed_day_slices(g_start, end, GDELT_SLICE_DAYS):
                    out.append(PlannedSlice(name, spec.kind, spec.entity_id, spec.entity_name, query, a, b))
                continue
            months = WIDTH_MONTHS.get((name, spec.kind))
            if months is None:
                continue
            start = cfg.start
            if name == "youtube":
                start = max(start, dt.date(cfg.youtube_start_year, 1, 1))
            for a, b in slicing.calendar_slices(start, end, months):
                out.append(PlannedSlice(name, spec.kind, spec.entity_id, spec.entity_name, query, a, b))
    return out


def _utc(d: dt.date) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


def _insert_ignore(db, rows: List[Dict[str, Any]]) -> None:
    """INSERT ... ON CONFLICT DO NOTHING on the slice unique key (Postgres in prod, sqlite in unit tests)."""
    from app.models.backfill import BackfillSlice
    if not rows:
        return
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(BackfillSlice).values(rows).on_conflict_do_nothing(
        index_elements=["client_id", "source", "query", "slice_start", "slice_end"]
    )
    db.execute(stmt)


def seed_slices(db, client_id, planned: List[PlannedSlice]) -> int:
    import uuid
    from app.models.backfill import BackfillSlice
    before = db.query(BackfillSlice).filter(BackfillSlice.client_id == client_id).count()
    rows = [dict(id=uuid.uuid4(), client_id=client_id, entity_id=(uuid.UUID(str(p.entity_id)) if p.entity_id else None), entity_name=p.entity_name,
                 source=p.source, query=p.query, slice_start=_utc(p.start), slice_end=_utc(p.end),
                 status="PENDING", attempts=0) for p in planned]
    for i in range(0, len(rows), 500):
        _insert_ignore(db, rows[i:i + 500])
    db.commit()
    return db.query(BackfillSlice).filter(BackfillSlice.client_id == client_id).count() - before


# ------------------------------------------------------------------- ingestion
def get_or_create_backfill_source(db, client_id, src: SourceDef):
    """
    One `sources` row per (client, source), url `backfill://<client_id>/<source>`.
    The synthetic URL is deliberately not any rss_feeds.feed_url, so the live
    pipeline's "pick up PENDING docs from this client's feeds" sweep never
    sees backfilled documents (they are fed to NLP by drain_backfill_nlp).
    """
    from sqlalchemy.exc import IntegrityError
    from app.models.source import Source, SourceCategory
    url = f"backfill://{client_id}/{src.name}"
    row = db.query(Source).filter(Source.url == url).first()
    if row:
        return row
    cat = db.query(SourceCategory).filter(SourceCategory.name == src.category).first()
    if not cat:
        cat = SourceCategory(name=src.category, base_reliability_score=1.0)
        db.add(cat)
        db.commit()
        db.refresh(cat)
    labels = {"google_news": "Google News (history)", "youtube": "YouTube (history)",
              "gdelt": "GDELT (history)", "hn": "Hacker News (history)"}
    db.add(Source(category_id=cat.id, name=labels.get(src.name, src.name), source_type=src.document_type,
                  url=url, schedule_cron="on-demand", is_active=False))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return db.query(Source).filter(Source.url == url).first()


def ingest_items(db, client_id, src: SourceDef, raw_items: List[Dict[str, Any]],
                 now: Optional[dt.datetime] = None, terms: Optional[List[str]] = None) -> Dict[str, int]:
    """
    Normalise + persist through the normal path (process_and_save_document:
    ON CONFLICT DO NOTHING dedup on canonical url / content_hash, then inline
    entity matching). Items without a real published date are skipped, never
    defaulted to "now". When `terms` is given, items whose title/summary name neither
    the brand nor a tracked entity are dropped BEFORE anything is saved.
    """
    from app.schemas.document import NormalizedDocument
    from app.services.document_service import process_and_save_document

    now = now or dt.datetime.now(dt.timezone.utc)
    source = get_or_create_backfill_source(db, client_id, src)
    adapter = load_adapter(src)
    stats = {"seen": len(raw_items), "saved": 0, "deduped": 0, "skipped_undated": 0, "skipped_future": 0, "failed": 0,
             "dropped_irrelevant": 0}
    for raw in raw_items:
        try:
            norm = adapter.normalize(raw, str(source.id))
            pub = norm.get("published_at")
            if pub is None:
                stats["skipped_undated"] += 1
                continue
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=dt.timezone.utc)
                norm["published_at"] = pub
            if pub > now + dt.timedelta(days=2):
                stats["skipped_future"] += 1
                continue
            if not norm.get("url"):
                stats["failed"] += 1
                continue
            if terms and not is_relevant(norm.get("title"), norm.get("content"), terms):
                stats["dropped_irrelevant"] += 1
                continue
            is_saved, _, _ = process_and_save_document(db, NormalizedDocument(**norm))
            stats["saved" if is_saved else "deduped"] += 1
        except Exception as e:   # one bad item must not lose the slice
            db.rollback()
            stats["failed"] += 1
            logger.warning("backfill_item_failed", source=src.name, error=str(e)[:200])
    return stats


# ------------------------------------------------------------------------ run
def run_client(db, client_id, cfg: BackfillConfig, ctx: Optional[Dict[str, Any]] = None,
               fetchers: Optional[Dict[str, Callable]] = None,
               ingest: Optional[Callable] = None) -> Dict[str, Any]:
    """
    Process up to cfg.max_slices_per_run PENDING slices. Returns a summary with
    `remaining` (PENDING slices left) and `paused` (reason, if a source budget stopped the run).
    Finished slices (DONE/SPLIT) are never refetched.
    """
    from app.models.backfill import BackfillSlice
    ctx = ctx if ctx is not None else {"youtube_units_budget": cfg.youtube_units_budget}
    ingest = ingest or ingest_items
    from app.services.backfill import control
    specs = build_queries(db, client_id, cfg.include_competitors, cfg.include_products, list(cfg.exclude_entities))
    seeded = seed_slices(db, client_id, plan_slices(specs, cfg))
    terms = tracked_terms(db, client_id, cfg.include_competitors, cfg.include_products) if cfg.relevance_filter else None
    ing_kwargs = {"terms": terms} if terms else {}
    # query kind per (source, query) so slices can be taken brand/risk first, executives next
    kind_by_query = {(name, getattr(sp, SOURCES[name].query_attr)): sp.kind for sp in specs for name in cfg.sources}

    summary: Dict[str, Any] = {"seeded": seeded, "processed": 0, "done": 0, "split": 0, "errors": 0,
                               "saved": 0, "deduped": 0, "skipped_undated": 0, "dropped_irrelevant": 0, "paused": None,
                               "unavailable": [], "stopped": False}
    skip_sources = set()
    tried = set()      # a slice is attempted at most once per run (no hot retry loop); failures wait for the next run
    def _priority(r):
        # (tier, source, newest first): brand and risk words first, then people, competitors/products last
        kind = kind_by_query.get((r.source, r.query), "executive")
        return (KIND_PRIORITY.get(kind, 9), SOURCE_PRIORITY.get(r.source, 9), -r.slice_end.timestamp())

    while summary["processed"] < cfg.max_slices_per_run:
        if control.is_stopped():
            summary["stopped"] = True
            break
        q = db.query(BackfillSlice.id, BackfillSlice.source, BackfillSlice.query, BackfillSlice.slice_end).filter(
            BackfillSlice.client_id == client_id, BackfillSlice.status == "PENDING",
            BackfillSlice.source.in_(list(cfg.sources)),
        )
        if skip_sources:
            q = q.filter(~BackfillSlice.source.in_(list(skip_sources)))
        if tried:
            q = q.filter(~BackfillSlice.id.in_(list(tried)))
        candidates = q.all()
        if not candidates:
            break
        row = db.get(BackfillSlice, min(candidates, key=_priority).id)
        tried.add(row.id)
        src = SOURCES[row.source]
        fetch = (fetchers or {}).get(row.source, src.fetch)
        s, e = row.slice_start.date(), row.slice_end.date()
        try:
            raw = fetch(row.query, s, e, ctx)
        except QuotaPaused as qp:
            summary["paused"] = str(qp)
            if "YouTube" in str(qp):
                skip_sources.add(row.source)     # other sources can keep going
                continue
            break
        except SourceUnavailable as su:
            skip_sources.add(row.source)
            summary["unavailable"].append(f"{row.source}: {su}")
            continue
        except Exception as ex:
            db.rollback()
            row = db.get(BackfillSlice, row.id)
            row.attempts = (row.attempts or 0) + 1
            row.error = str(ex)[:500]
            if row.attempts >= cfg.max_attempts:
                row.status = "ERROR"
                summary["errors"] += 1
            db.commit()
            summary["processed"] += 1
            continue

        st = ingest(db, client_id, src, raw, **ing_kwargs)
        row = db.get(BackfillSlice, row.id)
        row.item_count = len(raw)
        row.new_count = st["saved"]
        row.error = None
        row.attempts = (row.attempts or 0) + 1
        children = []
        if slicing.needs_split(len(raw), src.cap):
            halves = slicing.split_slice((s, e))
            if halves:
                children = halves
        if children:
            row.status = "SPLIT"
            _insert_ignore(db, [dict(id=__import__("uuid").uuid4(), client_id=client_id, entity_id=row.entity_id,
                                     entity_name=row.entity_name, source=row.source, query=row.query,
                                     slice_start=_utc(a), slice_end=_utc(b), status="PENDING", attempts=0)
                                for a, b in children])
            summary["split"] += 1
        else:
            row.status = "DONE"
            summary["done"] += 1
        db.commit()
        summary["processed"] += 1
        for k in ("saved", "deduped", "skipped_undated", "dropped_irrelevant"):
            summary[k] += st.get(k, 0)
        logger.info("backfill_slice_done", client_id=str(client_id), source=row.source, query=row.query[:80],
                    slice_start=str(s), slice_end=str(e), fetched=len(raw), saved=st.get("saved", 0),
                    deduped=st.get("deduped", 0), dropped_irrelevant=st.get("dropped_irrelevant", 0),
                    undated=st.get("skipped_undated", 0), status=row.status)

    summary["remaining"] = db.query(BackfillSlice).filter(
        BackfillSlice.client_id == client_id, BackfillSlice.status == "PENDING",
        BackfillSlice.source.in_(list(cfg.sources)),
    ).count()
    summary["youtube_units_used"] = ctx.get("youtube_units_used", 0)
    return summary


# -------------------------------------------------------------------- dry run
# Items-per-slice assumptions used only when --probe is not given. The Google News
# figures are the Godrej monthly counts measured on 2026-10-17 (9,9,10,14,10,35,36 -> avg 17.6).
ASSUMED_ITEMS_PER_MONTH = {
    ("google_news", "brand"): 17.6, ("google_news", "risk"): 4.0, ("google_news", "executive"): 1.5,
    ("google_news", "competitor"): 10.0, ("google_news", "product"): 1.0,
    ("youtube", "brand"): 5.0, ("youtube", "risk"): 0.5, ("youtube", "executive"): 0.3,
    ("youtube", "competitor"): 3.0, ("youtube", "product"): 0.3,
    ("hn", "brand"): 0.3, ("hn", "executive"): 0.05, ("hn", "competitor"): 0.2, ("hn", "product"): 0.05,
}


def dry_run(db, client_id, cfg: BackfillConfig, probe: int = 0,
            probe_fetch: Optional[Callable] = None) -> Dict[str, Any]:
    """
    Reports slices/calls/quota/time for a client. READ-ONLY on the DB (no
    seeding, no inserts) and makes zero paid calls. `probe` > 0 additionally
    does up to that many FREE Google News GETs to measure items-per-slice
    instead of using the assumptions above.
    """
    import random
    from app.models.backfill import BackfillSlice
    from app.models.client import Client

    client = db.query(Client).filter(Client.id == client_id).first()
    specs = build_queries(db, client_id, cfg.include_competitors, cfg.include_products, list(cfg.exclude_entities))
    planned = plan_slices(specs, cfg)

    done_keys = set()
    for r in db.query(BackfillSlice).filter(BackfillSlice.client_id == client_id, BackfillSlice.status.in_(("DONE", "SPLIT", "SKIPPED"))).all():
        done_keys.add((r.source, r.query, r.slice_start.date(), r.slice_end.date()))
    todo = [p for p in planned if (p.source, p.query, p.start, p.end) not in done_keys]

    # optional free probe of Google News density per kind
    probed: Dict[str, float] = {}
    if probe and probe_fetch is None:
        from app.services.backfill.fetchers import fetch_google_news
        probe_fetch = fetch_google_news
    if probe:
        rng = random.Random(7)
        for kind in sorted({p.kind for p in todo if p.source == "google_news"}):
            pool = [p for p in todo if p.source == "google_news" and p.kind == kind]
            sample = rng.sample(pool, min(max(1, probe // 3), len(pool)))
            counts = []
            for p in sample:
                try:
                    counts.append(min(len(probe_fetch(p.query, p.start, p.end, {})), 100))
                except Exception:
                    pass
            if counts:
                probed[kind] = sum(counts) / len(counts)

    by_source: Dict[str, Dict[str, Any]] = {}
    est_docs = 0.0
    for p in todo:
        d = by_source.setdefault(p.source, {"slices": 0, "est_items": 0.0})
        d["slices"] += 1
        months = max(1.0, (p.end - p.start).days / 30.4)
        if p.source == "google_news" and p.kind in probed:
            per_slice = probed[p.kind]
        elif p.source == "gdelt":
            per_slice = 8.0                                   # ASSUMPTION
        else:
            per_slice = ASSUMED_ITEMS_PER_MONTH.get((p.source, p.kind), 1.0) * months
        d["est_items"] += per_slice
    for name, d in by_source.items():
        d["est_items"] = round(d["est_items"])
        est_docs += d["est_items"]

    yt_slices = by_source.get("youtube", {}).get("slices", 0)
    yt_calls = yt_slices * 1.3                                # ASSUMPTION: extra pages + splits
    yt_units = round(yt_calls * 101)                          # 100 search.list + 1 videos.list
    from app.services.backfill.fetchers import YT_BACKFILL_DAILY_CEILING
    per_day = max(1, YT_BACKFILL_DAILY_CEILING - 1200)        # leave room for ~2 live pipeline runs/day
    gd = by_source.get("gdelt", {}).get("slices", 0)
    gn = by_source.get("google_news", {}).get("slices", 0)
    hn = by_source.get("hn", {}).get("slices", 0)
    fetch_seconds = gn * 1.5 + gd * 6.5 + hn * 1.0 + yt_calls * 0.8
    return {
        "client": client.name if client else str(client_id),
        "start": cfg.start.isoformat(), "end": cfg.effective_end().isoformat(),
        "queries": [{"kind": s.kind, "entity": s.entity_name} for s in specs],
        "planned_slices": len(planned), "already_done": len(planned) - len(todo), "slices_to_fetch": len(todo),
        "by_source": by_source,
        "google_news_calls": gn, "gdelt_calls": gd, "hn_calls": hn,
        "youtube_calls_est": round(yt_calls), "youtube_units_est": yt_units,
        "youtube_days_at_budget_est": round(yt_units / per_day, 1),
        "fetch_time_minutes_est": round(fetch_seconds / 60, 1),
        "est_new_documents": round(est_docs),
        "nlp_docs_capped": min(round(est_docs), bf_settings.MAX_PROCESS_DOCS_PER_CLIENT),
        "nlp_hours_at_measured_rate": round(min(est_docs, bf_settings.MAX_PROCESS_DOCS_PER_CLIENT) / NLP_DOCS_PER_HOUR_MEASURED, 1),
        "density_source": {"google_news": ("probe" if probed else "assumption"), "others": "assumption"},
        "probed_items_per_slice": {k: round(v, 1) for k, v in probed.items()},
        "paid_calls": 0, "db_writes": 0,
    }
