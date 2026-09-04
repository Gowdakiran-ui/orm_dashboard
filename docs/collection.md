# Collection Layer

Reference doc for the collection layer of the ORM Intelligence Platform:
pulling raw documents from RSS/JSON news sources and getting them into
`documents` for the processing/NLP layer. Written for both human engineers
and AI coding agents — every claim below was checked against live code and
the live dev DB as of 2026-08-09, not written from memory of past migrations
or prior audit docs. See section 9 for how to re-verify any of this.

> **2026-09-04 update (Run-Pipeline-gated architecture):** the "Scheduled
> path" described in sections 1–2 below (`schedule_feeds` firing every
> minute) has been **removed from `beat_schedule`** — collection now only
> ever happens via the Manual path (`_stage_collect` inside
> `run_client_pipeline`), triggered by a client's own "Run Pipeline"
> action. `schedule_feeds`/`fetch_feed_task` still exist as functions (not
> deleted) but are unreachable except by direct manual invocation. This
> was a deliberate business decision (metered/paid sources — YouTube,
> a planned Meta integration — made "poll everything every minute
> regardless of activity" cost real money) — see `celery_app.py`'s module
> docstring for the current architecture. Sections 1–2's internals (how
> `_stage_collect`/`fetch_feed_task` normalize and dedupe) are still
> accurate; the "two independent entry points" framing and the beat
> schedule table in section 7 are not — corrected inline below.

**Out of scope:** processing/NLP internals, reputation engine internals,
frontend/API layers (beyond noting where collection hands off to them).

---

## 1. Overview

The collection layer fetches raw content (RSS feeds, GDELT news-search
results, Hacker News stories) on a schedule or on demand, normalizes it into
a common document shape, deduplicates it against what's already stored, and
persists it to `documents`. From there it hands off to the processing/NLP
layer (entity matching, topic classification, sentiment analysis — not
covered in this doc) by enqueuing `process_document_intelligence`.

There is **one entry point** into collection (as of the 2026-09-04
Run-Pipeline-gated redesign — see the update note above):

- **Manual path** — `POST /clients/{client_id}/pipeline/run` dispatches
  `run_client_pipeline`, whose first stage (`_stage_collect`) collects only
  that client's own feeds synchronously, in-process, as part of a larger
  on-demand intelligence pipeline run (collection → processing → trend →
  risk → alert → narrative → reputation → executive → benchmark).

A **scheduled path** existed previously — Celery Beat fired
`schedule_feeds` every minute, enqueuing `fetch_feed_task` per due feed,
async and independent of any client action. It is documented in section 2
below (the mechanics are unchanged in the code, just unreachable now) since
`fetch_feed_task`/`process_document_task` are still the functions the
manual path's `_stage_collect` conceptually mirrors, and understanding the
old async shape helps explain some of the schema fields (`last_polled_at`
etc.) still in use.

---

## 2. Architecture (current, both paths)

### Scheduled path (async, all active feeds) — REMOVED from beat_schedule 2026-09-04, mechanics below no longer run

```
Celery Beat (every minute)
    │
    ▼
schedule_feeds()                              [collection_tasks.py]
    │  - Redis lock (nx, 600s) so overlapping cycles don't double-schedule
    │  - for each active RSSFeed:
    │      skip if not due yet (poll_interval_minutes)
    │      skip if a CollectionJob is already created/collecting/processing
    │      for this feed's rss_feeds.id
    │  - apply_async(fetch_feed_task, feed_id) in batches of 5,
    │    10s stagger between batches
    ▼
fetch_feed_task(feed_id)   [queue: io_queue, bind=True, max_retries=3]
    │  1. create CollectionJob (status=created → collecting)
    │  2. adapter = ADAPTER_REGISTRY[feed.source_format]()
    │  3. entries = adapter.fetch(feed.feed_url)      ← network call
    │  4. source = _get_or_create_source(feed)         (INSERT..ON CONFLICT)
    │  5. _record_source_health(source.id, success=True)
    │  6. walk entries, stop at feed.last_entry_guid (incremental poll)
    │  7. update feed.last_polled_at / last_entry_guid
    │  8. for each new entry:
    │         raw_payload = json.dumps(entry)   ← FeedParserDict → JSON
    │         process_document_task.delay(job_id, source.id, raw_payload, ...)
    │
    │  on exception: job marked failed BY PRIMARY KEY (job_id captured up
    │  front, not "most recent job for this source_id" — see D8 in
    │  FINDINGS.md); on exhausted retries, _record_source_health(success=False)
    ▼
process_document_task(job_id, source_id, raw_payload_json, ...) [queue: cpu_queue]
    │  1. raw_data = json.loads(raw_payload_json)   ← plain dict now, NOT
    │     the original FeedParserDict (see section 4/8 for why this matters)
    │  2. adapter = ADAPTER_REGISTRY[source_format]()
    │  3. normalized = adapter.normalize(raw_data, source_id)
    │  4. process_and_save_document(normalized)      → INSERT..ON CONFLICT
    │     DO NOTHING against documents (dedup, section 6)
    │  5. if saved: process_document_intelligence.delay(doc_id, client_id, job_id)
    │     ── hands off to the processing/NLP layer here ──
    │  6. update CollectionJob counters (documents_saved/deduplicated/failed)
```

### Manual path (sync, one client's feeds only)

```
POST /clients/{client_id}/pipeline/run     [api/endpoints/clients.py]
    │  - creates PipelineRun row (status=QUEUED)
    │  - celery_app.send_task(run_client_pipeline, run_id, client_id)
    │  - returns 202 immediately
    ▼
run_client_pipeline(run_id, client_id)     [queue: pipeline_queue]
    │  - acquires Redis lock pipeline:lock:{client_id} (NX, 2h TTL)
    ▼
_stage_collect(ctx, db)                    [aggregation_tasks.py]
    │  - client_feeds = RSSFeed WHERE client_id = ctx.client_id
    │    (topical_global feeds have client_id=NULL — correctly excluded)
    │  - for each feed, IN-PROCESS, no Celery dispatch:
    │      source = _get_or_create_source(feed)   (same function as async path)
    │      adapter = ADAPTER_REGISTRY[feed.source_format]()
    │      entries = adapter.fetch(...)
    │      for entry: norm = adapter.normalize(entry, source.id)  ← entry is
    │           the LIVE adapter object here, never JSON-round-tripped
    │      process_and_save_document(norm)
    │  - also picks up any Document rows already processing_status=PENDING
    │    for this client's sources
    │  - returns list of doc IDs → next pipeline stage (_stage_process)
    │    hands off to processing/NLP from there
```

The key structural difference: the async path serializes each entry to
JSON and back (Redis → separate worker process) before normalizing;
the sync path normalizes directly against the adapter's live return value.
This is why a normalize() bug that only shows up on the JSON-round-tripped
shape (see section 8) affects only the scheduled path.

---

## 3. Source types

`rss_feeds` has two independent discriminator columns. `source_type`
describes ownership/scope; `source_format` describes wire format (what the
adapter must parse). Both are DB-level `CHECK` constraints, not just
convention — confirmed via `pg_constraint`.

| `source_type` | Meaning | `source_format` values seen with it |
|---|---|---|
| `entity_search` | Per-client Google News RSS search feed | `rss` |
| `topical_global` | Global/topical feed, no single owning client (`client_id IS NULL`) | `rss` |
| `json_api` | Per-client JSON search API feed | `gdelt_json`, `hn_algolia_json` |

| `source_format` | Adapter class | Wire format |
|---|---|---|
| `rss` | `RSSAdapter` (`app/adapters/rss.py`) | RSS/Atom XML via `feedparser` |
| `gdelt_json` | `GDELTAdapter` (`app/adapters/gdelt.py`) | GDELT DOC 2.0 JSON (`{"articles": [...]}`) |
| `hn_algolia_json` | `HNAlgoliaAdapter` (`app/adapters/hn_algolia.py`) | HN Algolia search JSON (`{"hits": [...]}`) |

Both columns default to `entity_search`/`rss` respectively. Dispatch is a
single dict lookup in `app/adapters/registry.py`:
`ADAPTER_REGISTRY.get(feed.source_format, RSSAdapter)`.

**Live distribution** (32 `rss_feeds` rows, 2026-08-09):

| source_type | source_format | count |
|---|---|---|
| entity_search | rss | 7 |
| json_api | gdelt_json | 6 |
| json_api | hn_algolia_json | 6 |
| topical_global | rss | 13 |

---

## 4. Adapters

All adapters live in `app/adapters/`. Two interfaces exist:

- `BaseAdapter` (`base.py`) — `fetch(feed_url, **kwargs) -> list[dict]`,
  `normalize(raw_data, source_id, **kwargs) -> dict`. Used by the collection
  entry points above.
- `BaseSearchAdapter` (`search_base.py`) — `search(keyword, cursor, **kwargs)
  -> (list[dict], cursor)`, `normalize(raw_data, source_id, **kwargs) ->
  dict`. Used only by `search_tasks.py` (out of scope for this doc).

| File | Class | Interface | Fetches from | Status |
|---|---|---|---|---|
| `rss.py` | `RSSAdapter` | `BaseAdapter` | Any RSS/Atom URL via `feedparser`; raises on HTTP≥400 or feed parse error | **Active** — default adapter, used by both entry points |
| `rss.py` | `GoogleNewsRSSAdapter(RSSAdapter)` | `BaseAdapter` | Same as `RSSAdapter`, no behavior override | Defined but not selected by the registry (registry maps `"rss"` to `RSSAdapter` directly); still constructible if referenced directly |
| `gdelt.py` | `GDELTAdapter` | `BaseAdapter` | GDELT DOC 2.0 `doc/doc` JSON endpoint | **Active** — used for `json_api`/`gdelt_json` feeds. No article body text available, `content` falls back to `title`. Confirmed live: GDELT 429s on requests <~5s apart |
| `hn_algolia.py` | `HNAlgoliaAdapter` | `BaseAdapter` | HN Algolia `search` JSON endpoint | **Active** — used for `json_api`/`hn_algolia_json` feeds. `content` falls back to `story_text` (self-posts only) then `title` |
| `reddit.py` | `RedditAdapter` | `BaseSearchAdapter` | Reddit via PRAW | **Implemented but inactive.** No `rss_feeds`/`sources` row references it, no scheduled task calls it, `source_format` has no `reddit` value in its `CHECK` constraint. A future agent should not assume this is wired up. |
| `youtube.py` | `YouTubeAdapter` | `BaseSearchAdapter` | YouTube Data API v3 search | **Implemented but inactive.** Same as Reddit — no live wiring, no `source_format` value for it. |

---

## 5. Database schema (collection-relevant tables)

Column/constraint definitions below are from live `information_schema` /
`pg_constraint` introspection on the dev DB, not from migration files —
migrations, `schema.sql`, and the SQLAlchemy models are three separate
artifacts that can drift; only the live DB is authoritative for what's
actually enforced right now.

### `rss_feeds` — one row per pollable feed

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | NO | PK |
| `feed_name`, `feed_url` | varchar | NO | `feed_url` has `UNIQUE` |
| `category` | varchar(50) | yes | free text |
| `poll_interval_minutes` | int | yes | used by `schedule_feeds` due-check |
| `client_id` | uuid | yes | FK → `clients.id` `ON DELETE SET NULL`. NULL for `topical_global` feeds |
| `source_type` | varchar(20) | NO | `CHECK IN ('entity_search','topical_global','json_api')` |
| `source_format` | varchar(20) | NO | `CHECK IN ('rss','gdelt_json','hn_algolia_json')` |
| `is_active` | bool | yes | `schedule_feeds` only polls `is_active=true` |
| `last_polled_at`, `last_entry_guid`, `last_entry_published_at` | timestamptz / **text** / timestamptz | yes | incremental-poll cursor. `last_entry_guid` is `text` (unbounded) — was `VARCHAR(512)` until a real Google News redirect GUID (732+ chars) hit `StringDataRightTruncation` in testing; widened, no cap |
| `reliability_score` | float | yes | not currently written anywhere found — treat as unpopulated/legacy until confirmed otherwise |
| `extract_full_article` | bool | yes | passed through to `process_document_task`; the actual extraction logic is a no-op placeholder in `document_processor.py` today |

**Writers:** `schedule_feeds`/`fetch_feed_task` (poll state), `onboard_client`
(creates new feeds for new clients), `seed_topical_feeds.sql` (static
seed). **Readers:** `schedule_feeds`, `fetch_feed_task`, `_stage_collect`.

### `sources` — one row per distinct collected URL

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | NO | PK |
| `category_id` | uuid | yes | FK → `source_categories.id` |
| `name`, `source_type` | varchar | NO | `source_type` here is free text (e.g. `"rss"`, `feed.source_format` value), **not** DB-constrained like `rss_feeds.source_type` |
| `url` | varchar(1024) | yes | **`UNIQUE`** |
| `schedule_cron` | varchar(50) | NO | not read by the Celery-based scheduler; likely a legacy/pre-Celery field |

`documents.source_id` and `source_health.source_id` both FK to
`sources.id`. **`collection_jobs.source_id` FKs to `rss_feeds.id`, NOT
`sources.id`, despite the column name** — this is a real, confirmed naming
trap; don't assume `collection_jobs.source_id` joins to `sources`.

`sources` rows are created lazily on a feed's first successful poll via
`_get_or_create_source()` (shared by both entry points, `collection_tasks.py`),
using `INSERT ... ON CONFLICT (url) DO NOTHING` + `SELECT` — safe under
concurrent pollers racing the same URL. A feed that has never successfully
polled has no `sources` row yet; this is expected, not a bug (21 of 32
`rss_feeds` rows currently have no matching `sources` row, live-confirmed).

### `documents` — the actual collected content

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | NO | PK |
| `url` | text | NO | **`UNIQUE`** |
| `content_hash` | varchar(64) | yes | **`UNIQUE`** — SHA256 of `normalized_content`, see section 6 |
| `source_id` | uuid | yes | FK → `sources.id` |
| `document_type` | varchar(50) | yes | adapter's `source_type` value (`"rss"`, `"gdelt"`, `"hn_algolia"`) |
| `published_at` | timestamptz | yes | see section 8 for a known-NULL population |
| `collected_at` | timestamptz | yes | `server_default now()`, also set explicitly by adapters |
| `processing_status` | varchar(20) | yes | `CHECK IN ('PENDING','PROCESSING','MATCHED','FAILED','SKIPPED','RETRYING','COMPLETED')` — handoff point to processing layer |
| `match_*`, `topic_*`, `sentiment_*` columns | — | — | processing-layer state, out of scope for this doc |

### `collection_jobs` — one row per feed poll attempt

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `job_id` | uuid | NO | PK |
| `source_id` | uuid | NO | FK → **`rss_feeds.id`** `ON DELETE CASCADE` (see the naming-trap note above) |
| `status` | varchar(50) | yes | not DB-constrained; observed values: `created`, `collecting`, `processing`, `completed`, `failed` |
| `documents_found/saved/matched/deduplicated/failed` | int | yes | counters updated across both `fetch_feed_task` and `process_document_task` |

### `source_health` — per-source reliability tracking

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | uuid | NO | PK |
| `source_id` | uuid | NO | FK → `sources.id` `ON DELETE CASCADE`, **`UNIQUE`** — one row per source |
| `status` | varchar(50) | yes | writer uses `"healthy"` / `"failing"`; not DB-constrained |
| `reliability_penalty` | numeric | yes | 0.0–1.0 fraction; read by `reputation_engine.py` (~line 249) as `(base_reliability_score - reliability_penalty) * 100`, per-source, joined via `Source.id == SourceHealth.source_id` |
| `consecutive_failures` | int | yes | resets to 0 on success |
| `last_success_at` | timestamptz | yes | preserved through failures, only updated on success |

Written by `_record_source_health()` (`collection_tasks.py`), called from
`fetch_feed_task` on every successful fetch and on exhausted-retry failure
(not on every transient retry). Only the async scheduled path writes this —
`_stage_collect` (manual path) does not call it. Currently **1 row** live
(the table had zero writers at all until recently; see section 8).

---

## 6. Deduplication

Two independent dedup layers, both enforced at the SQL constraint level via
a single `INSERT ... ON CONFLICT DO NOTHING` (no explicit `index_elements`,
so it fires on **either** conflicting unique constraint):

```python
# app/services/document_service.py — process_and_save_document()
stmt = insert(Document).values(...).on_conflict_do_nothing()
result = db.execute(stmt)
# result.rowcount == 0  →  treated as deduplicated, not an error
```

- **URL dedup**: `documents.url UNIQUE`. The URL is canonicalized first via
  `canonicalize_url()` (`app/utils/text_processing.py`), which **strips all
  query parameters and the fragment**, not just tracking params (`utm_*`
  etc.) — documented in the code itself as "keeping it simple for the
  milestone." Two URLs that differ only by query string (including
  meaningfully, not just tracking noise) will collapse to the same
  canonical URL and dedupe.
- **Content dedup**: `documents.content_hash UNIQUE`, SHA256 of
  `normalized_content` (`generate_content_hash()`, same file). Catches the
  same content reaching the pipeline via a different URL.

Both paths return `(is_saved=False, is_deduplicated=True, match_count=0)`
on conflict — no exception, no retry, no distinction between "duplicate by
URL" and "duplicate by content" in the return value.

`sources.url` and `source_health.source_id` use the same
`ON CONFLICT DO NOTHING`(-style upsert) pattern for their own dedup —
see section 5.

---

## 7. Scheduling & reliability

### Celery Beat schedule (collection-relevant entries only)

As of the 2026-09-04 Run-Pipeline-gated redesign, `schedule_feeds` and
`schedule_searches` are no longer in `beat_schedule` — collection only
happens inside `run_client_pipeline`'s chain. Real, live schedule
(confirmed by dumping the running celery-beat container's
`celery_app.conf.beat_schedule`, not just reading the source):

| Beat key | Task | Queue | Frequency |
|---|---|---|---|
| `flush-metrics-every-5-minutes` | `collection_tasks.flush_metrics_task` | `io_queue` | every 5 min |
| `collection-watchdog-every-30-minutes` | `collection_tasks.collection_watchdog` | `io_queue` | every 30 min (loosened from 15 min — collection jobs are now created by individual Run Pipeline triggers, not a perpetual once-a-minute process, so a stuck job is lower-urgency to catch) |
| `feed-revival-watchdog-every-hour` | `collection_tasks.feed_revival_watchdog` | `io_queue` | every hour |

`fetch_feed_task` and `schedule_feeds` are no longer dispatched by any beat
entry; `_stage_collect` (inside `run_client_pipeline`) is the only live
collection entry point, and calls the same `adapter.fetch()` /
`process_and_save_document()` logic in-process instead of dispatching
`fetch_feed_task`/`process_document_task` as separate Celery tasks.
`document_processor.process_document_task` and `fetch_feed_task` still
exist (not deleted) but are unreachable without a beat entry or manual
invocation.
`run_client_pipeline` (manual path) runs on its own isolated
`pipeline_queue`.

### Retry/backoff

`fetch_feed_task` and `process_document_task` are both `bind=True,
max_retries=3` with exponential backoff `60 * (2 ** retries)` seconds
(60s, 120s, 240s). On exhausted retries, `fetch_feed_task` records a
`source_health` failure (section 5); on any exception (including
mid-retry), the current `CollectionJob` is marked `failed` **by its actual
primary key**, captured at job creation — not by querying "most recent job
for this `source_id`", which would misattribute failures under concurrent
runs for the same feed.

### Watchdog

`collection_watchdog` (`collection_tasks.py`) finds `CollectionJob` rows
`status IN ('collecting','processing')` with `started_at` older than a
2-hour hardcoded timeout, marks them `failed`, cleans up their Redis
progress keys, and releases the triggering client's pipeline lock if it's
safe to do so (lock value starts with `scheduled-`/`sync-` or is
`success`/`failed` — won't clobber an active manual run's lock). Runs every
15 minutes per the Beat entry above.

### `source_health`

Covered in section 5. Scoring is a simple, deliberately-chosen linear
penalty (`min(1.0, consecutive_failures * 0.2)`) — there's no prior
production scoring logic it was matched against beyond the read-side
formula in `reputation_engine.py`; treat the exact curve as provisional if
it turns out to need tuning.

---

## 8. Known limitations / open items

- **29 of 1226 `documents` rows have `published_at IS NULL`.** These
  predate a fix to `RSSAdapter.normalize()` (it used to check
  `hasattr(raw_data, 'published_parsed')`, which is always `False` on the
  plain `dict` that `raw_data` becomes after the async path's
  `json.dumps`/`json.loads` round-trip — `FeedParserDict` supports
  attribute access but a plain `dict` doesn't). The fix is in place
  (`.get('published_parsed')`, which works on both).
  **These 29 rows were deliberately NOT backfilled** — it's a data
  remediation decision, not something to "fix" by surprise. If you're
  touching date-based sorting/trend logic, know these rows exist.
- **This dev environment has no running Celery broker.** Calling a task's
  `.delay()`/`.apply_async()` (e.g. `fetch_feed_task` → `process_document_task`)
  raises `kombu.exceptions.OperationalError: Connection refused`. You can
  still exercise task bodies directly via `task_name.run(*args)` (bypasses
  Celery dispatch, runs synchronously in-process) to test everything up to
  the point of the next `.delay()` call, but you cannot verify a full
  async end-to-end round trip (scheduled path) without a real
  Redis/RabbitMQ broker running. The manual path (`_stage_collect`) is
  fully synchronous and unaffected by this — it never calls `.delay()` for
  collection itself, only for the intelligence handoff afterward.
- **Reddit/YouTube adapters exist but are not wired to any feed or
  scheduled task** (section 4). No `source_format` value routes to them.
- **`collection_jobs.source_id` FKs to `rss_feeds.id`, not `sources.id`,
  despite the column name being identical to `documents.source_id` and
  `source_health.source_id`, which both FK to `sources.id`.** Easy to
  assume otherwise; verified via `pg_constraint`, not documentation.
- **Content-hash dedup can silently over-collapse empty-content
  documents.** `generate_content_hash("")` returns `""`, and
  `documents.content_hash` is `UNIQUE`. Any second document whose
  extracted content is empty (e.g. a link post with no title/summary/body)
  will violate that constraint and get treated as a "deduplicate", even
  though it isn't actually a duplicate of the first empty-content
  document — it just also happened to produce no content. **Confirmed
  live: 1 document currently has `content_hash = ''`** — this is not
  theoretical.
- **`canonicalize_url()` strips all query parameters and the fragment**,
  not just tracking parameters. Two genuinely different URLs that differ
  only by query string will dedupe as the same document.
- **`sources.schedule_cron`** is a `NOT NULL` column populated on every
  insert (`"0 * * * *"` hardcoded) but not read anywhere found in the
  collection code paths — likely a legacy/pre-Celery field. Unclear —
  needs confirmation if it's read by something outside collection scope.
- **`GoogleNewsRSSAdapter`** (`rss.py`) is defined but the adapter registry
  never selects it (`"rss"` maps to plain `RSSAdapter`) — appears to be
  dead code, not confirmed with a full-repo grep as part of this doc.

---

## 9. How to verify this doc is still accurate

```sql
-- source_type / source_format live distribution (section 3)
SELECT source_type, source_format, COUNT(*) FROM rss_feeds GROUP BY 1, 2;

-- column/constraint ground truth for any table in section 5 (replace X)
SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'X';
SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'X'::regclass;

-- duplicate check (should be empty; both have UNIQUE constraints now)
SELECT url, COUNT(*) FROM sources GROUP BY url HAVING COUNT(*) > 1;
SELECT name, COUNT(*) FROM clients GROUP BY name HAVING COUNT(*) > 1;

-- known-limitations spot checks
SELECT COUNT(*) FROM documents WHERE published_at IS NULL;              -- should be >= 29
SELECT COUNT(*) FROM documents WHERE content_hash = '';                 -- empty-content dedup risk
SELECT COUNT(*) FROM rss_feeds f LEFT JOIN sources s ON f.feed_url = s.url WHERE s.id IS NULL; -- never-polled feeds

-- stuck-job / watchdog health
SELECT COUNT(*) FROM collection_jobs WHERE status IN ('collecting','processing') AND started_at < now() - interval '2 hours';

-- source_health population
SELECT COUNT(*) FROM source_health;

-- baseline row counts (section 5/8 context)
SELECT 'rss_feeds', COUNT(*) FROM rss_feeds UNION ALL
SELECT 'sources', COUNT(*) FROM sources UNION ALL
SELECT 'documents', COUNT(*) FROM documents UNION ALL
SELECT 'collection_jobs', COUNT(*) FROM collection_jobs UNION ALL
SELECT 'source_health', COUNT(*) FROM source_health;
```

```bash
# adapter registry has exactly one definition (no drifted duplicates)
grep -rn "ADAPTER_REGISTRY = {" app/adapters/ app/workers/

# beat schedule / retry config ground truth
grep -n "beat_schedule\|max_retries\|crontab" app/core/celery_app.py

# schema source of truth, current DB vs. schema.sql
python scripts/verify_environment.py

# confirm no datetime.utcnow() regressions
grep -rn "datetime.utcnow()" app/
```

If any of these return something different from what's written above, this
doc is stale on that point — trust the query result over the doc.
