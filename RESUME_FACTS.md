# RESUME_FACTS.md — XOOP / ORM Intelligence Platform

Refreshed 2026-10-14 from the repo at `main` (HEAD `0fb3fa2`; first written 2026-10-10 at `8a49029`). Every claim cites a file path or commit hash. Counts in §6 and §9 were re-measured on 2026-10-14; the other sections were carried over and spot-checked, not re-derived.
**I did not run the backend test suite** (see §10 — some tests may reach the production DB), did not hit the live site, and did not query the droplet. Anything labelled *live* below comes from a document written earlier, not from me.

**Evidence-tier legend**
- **[tracked]** file is committed in git, so the claim is reproducible from a clone.
- **[local-only]** file exists in the working tree but is **gitignored** (`.gitignore` lines for `audit/`, `reports/`, `stream_baseline.md`, `.build-*.log`; most root `*.md` forensics reports such as `PART_*.md`, `FINDINGS.md`, `NLP_AUDIT_*.md`, `XOOP_FEATURE_INVENTORY_*.md` are also not in `git ls-files`). They are your own notes. An interviewer cannot see them on GitHub, and you should not describe them as "in the repo".

---

## 1. One-paragraph description

XOOP (internally "ORM Intelligence Platform", Online Reputation Management) is a multi-tenant web platform that collects news, GDELT, Hacker News, YouTube, Instagram and Reddit coverage for a named company, matches each item to that company's brands, executives, products and competitors, scores sentiment, topic and risk with local transformer models plus a few LLM calls, and shows the result in a dashboard. The dashboard has a reputation score and grade, a risk register and matrix, alerts with AI summaries, competitor and executive comparison, and a raw intelligence stream. It is for PR, communications and risk teams (a super-admin manages client companies and users; a `client_user` sees only assigned companies). It replaces manually scanning press and social coverage with a scored, evidence-linked view. Evidence: `docker-compose.yml`, `orm_collection/app/**`, `orm_dashboard/src/**`, `orm_collection/app/core/auth.py`. The nav list (8 pages) is in `XOOP_FEATURE_INVENTORY_2026-09-24.md` [local-only], read from `orm_dashboard/src/components/Sidebar.tsx`.

Important framing: collection is **on demand, not continuous**. It runs only when a user clicks "Run Pipeline" (`orm_collection/app/core/celery_app.py` docstring, "Phase 15: Run-Pipeline-gated architecture"). Do not write "real-time monitoring" on a resume (see §10).

## 2. Architecture

1. **Frontend**: Next.js 16 / React 19 dashboard (`orm_dashboard/`). It polls per-client REST endpoints every 45 s (`orm_collection/app/core/dashboard_cache.py` docstring; `useDashboardData.ts`).
2. **API**: FastAPI app (`orm_collection/app/main.py`), about 60 route handlers in `app/api/endpoints/*.py`. Auth is a Redis-backed session cookie; per-request tenant check via `require_client_access` (`app/core/auth.py`).
3. **Trigger**: `POST .../run` creates a `pipeline_runs` row (QUEUED) and dispatches `run_client_pipeline` to Celery (`app/workers/aggregation_tasks.py` module docstring). It returns HTTP 202.
4. **Orchestrator** (`pipeline_queue`): takes a per-client Redis lock (`SET NX`, 2 h TTL, key `pipeline:lock:{client_id}`), then builds a Celery `chain`.
5. **Chain stages**, each on its own queue and each doing its own FSM transition:
   - COLLECTING (`io_queue`)
   - PROCESSING (`nlp_queue`, fan-out via chord)
   - RISK, ALERT, AI_SUMMARY, REPUTATION, EXECUTIVE, BENCHMARK (`aggregation_queue`; AI_SUMMARY orchestration sits on `pipeline_queue`)
   - FINALIZING (`pipeline_queue`)
   - Any stage failure fires a `link_error` handler that marks the run FAILED and releases the lock.
6. **Collection**: adapters (`app/adapters/`) fetch from RSS/Google News, GDELT, HN Algolia, YouTube Data API, and Instagram and Reddit via Apify. Documents are deduplicated at insert time (`document_service.py`) and matched to entities by the `flashtext` engine (`matching_engine.py`).
7. **NLP**: FinBERT sentiment, DistilBART-MNLI zero-shot topics over a 17-label taxonomy, spaCy NER entity discovery, and OpenRouter LLM calls for risk-role classification and per-item summaries.
8. **Storage**: PostgreSQL (37 tables, `database/schema.sql`, 2,079 lines) for all state. Redis is the Celery broker/result backend, session store, lock store, NLP result cache, dashboard cache and API-quota counters.
9. **Ops**: 10 containers via `docker-compose.yml` on one DigitalOcean droplet (`DEPLOY.md`). Beat runs only watchdogs, metrics flush and a daily backup (`celery_app.py` `beat_schedule`).

## 3. Tech stack (and why, where the repo says why)

| Area | Choice | Why (evidence) |
|---|---|---|
| Backend | Python 3.11, FastAPI 0.109, SQLAlchemy 2.0, Pydantic 2 (`requirements.txt`, `Dockerfile`) | no stated rationale |
| Async work | Celery 5.3 + Redis 7, 5 queues (`io`, `cpu`, `nlp`, `aggregation`, `pipeline`) | A single `--pool=solo --concurrency=1` worker let slow NLP block feed collection; split into per-resource workers (comment in `docker-compose.yml`, "celery-worker-general was split…") |
| DB | PostgreSQL, DigitalOcean managed + PgBouncer (`DATABASE_URL_POOLED`, `docker-compose.yml`); Render Postgres earlier (commit `70caa1d`, 2026-08-14); CI uses `postgres:18` | PgBouncer added to stay under `max_connections=25`; `docker-compose.yml` comments, 2026-09-05. Per-service pool sizes in commit `73099c7` |
| Schema mgmt | Raw `schema.sql` + numbered SQL migrations 0001–0013; Alembic removed | commit `70caa1d` "Remove alembic, adopt schema.sql as source of truth" |
| Sentiment | `ProsusAI/finbert` (`sentiment_analyzer.py`) | comment: "specifically trained for financial/business text" |
| Topics | `valhalla/distilbart-mnli-12-3` zero-shot (`topic_classifier.py`) | comment: "distilled BART MNLI for significantly faster CPU inference" |
| Entities | spaCy `en_core_web_sm` NER + `flashtext` keyword matching | no rationale found |
| LLM | OpenRouter `deepseek/deepseek-v4-pro` for risk-role gate (`risk_engine.py:~506`) and AI summaries (`ai_summary_engine.py:147`); Groq `llama-3.3-70b-versatile` for AI Advisor/Crisis Planner (`core/config.py:72`, `advisor/llm_providers.py`) | Calls are logged to `llm_call_log` (`utils/llm_call_logging.py`, migration 0007) |
| Torch | CPU-only wheel `torch==2.12.0+cpu` | droplet has no GPU; plain wheel pulled multi-GB CUDA deps and caused disk exhaustion (`CLAUDE.md`, commit `5c00a88`, 2026-09-24) |
| Social data | Apify actors (Instagram, Reddit); PRAW adapter dormant | Reddit self-service API registration closed (comment, `adapters/reddit_apify.py`) |
| Frontend | Next.js 16.2.9, React 19.2.4, Tailwind 4, Recharts, shadcn/base-ui, framer-motion, Vitest + jsdom (`orm_dashboard/package.json`) | no rationale found |
| Auth | bcrypt + opaque Redis sessions, httpOnly cookie, sliding TTL | "unlike a stateless JWT, logout can actually revoke" (`core/security.py` docstring) |
| Infra | Docker Compose on a DO droplet; AWS Copilot manifests exist (`copilot/`) | see §8, the AWS path is not evidenced as deployed |

## 4. Features actually implemented

Evidence for each is code present in a tracked file. "Verified live" only where an earlier report says so, and I flag that those reports are [local-only].

- [x] **Per-client Run-Pipeline orchestration** with FSM, chain, error handler and Redis lock: `workers/aggregation_tasks.py`, `models/pipeline_run.py` (`_ALLOWED_TRANSITIONS`).
- [x] **Concurrency guard** on pipeline start: `services/pipeline_service.py`, test `tests/test_pipeline_concurrency_guard.py`.
- [x] **RSS / Google News ingestion** (`adapters/rss.py`), **GDELT** (`gdelt.py`), **HN Algolia** (`hn_algolia.py`), via `adapters/registry.py`.
- [x] **YouTube search** with daily quota accounting and circuit breaker: `adapters/youtube.py`, `tests/test_youtube_quota.py`.
- [x] **Instagram and Reddit via Apify**: `adapters/instagram.py`, `reddit_apify.py`; tests `test_instagram_adapter.py`, `test_reddit_apify_adapter.py`. HEAD commit `8a49029` adds quoted-phrase search plus a mention filter.
- [x] **URL canonicalization + SHA-256 content-hash dedup** at insert: `utils/text_processing.py`, `services/document_service.py`; test `test_document_entity_dedupe.py`.
- [x] **HTML/boilerplate cleaning** (Google News outlet tag, Ars Technica footer links): `utils/text_processing.py::strip_html`.
- [x] **Keyword/alias entity matching with context-window confidence and negative-context rules** (e.g. Tesla/Meta/Tata disambiguation): `services/matching_engine.py::evaluate_match_accuracy`; `tests/test_matching_engine.py`.
- [x] **NER-based entity discovery** with candidate tables, layered org/person validators, advisory-lock dedup: `services/intelligence/entity_discovery.py` (2,701 lines), `entity_extractor.py`.
- [x] **FinBERT sentiment** with 512-token truncation fix (commit `3bdc988`), retry classification, mock-guard: `sentiment_analyzer.py`, `sentiment_batch_processor.py`; tests `test_sentiment_*.py`.
- [x] **Zero-shot topic classification** over 17 topics with a degenerate-all-topics guard (commit `e36d8ce`) and a batched-label forward pass: `topic_classifier.py`, `topic_classification_batch_processor.py`, `scripts/verify_topic_batching_equivalence.py`.
- [x] **NLP result cache in Redis** (30-day TTL, key = hash of text + model + labels): `core/nlp_cache.py`.
- [x] **Risk scoring**: `(topic_weight + sentiment_weight) / 140` scaled to 0–100, thresholds 25/50/75, source-reliability and reach/trust modifiers, plus an LLM SELF/BYSTANDER/EXONERATED gate: `core/risk_config.py`, `core/reach_trust_config.py`, `services/intelligence/risk_engine.py`; `tests/test_risk_engine.py`.
- [x] **Alert engine** with lifecycle states (NEW→ACTIVE→ACKNOWLEDGED→RESOLVED→CLOSED): `services/intelligence/alert_engine.py`, `api/endpoints/alerts.py`.
- [x] **Per-item AI summaries** (what / when / how-to-solve) with a content-signature cache so unchanged items are not re-billed: `ai_summary_engine.py::_content_signature`.
- [x] **Reputation score** (weighted 30-day composite with dynamic re-weighting and grade): `reputation_engine.py`; `tests/test_reputation_engine.py`.
- [x] **Executive reputation** and **promotion gate**: `executive_reputation_engine.py`, `tests/test_executive_promotion_gate.py`, `test_executive_reputation.py`.
- [x] **Competitor benchmark / share of voice / product benchmark**: `benchmark_engine.py` (1,099 lines), `models/competitor_benchmark.py`, `product_benchmark.py`; `tests/test_benchmark_engine.py`.
- [x] **Counterfeit detection** (deepfake image scan via Reality Defender; typosquat domains via WhoisFreaks + Bolster): `counterfeit_detection.py`, `models/counterfeit_scan.py`, migration `0010`. The Bolster contract is documented as "NOT independently confirmed" in the file's docstring.
- [x] **AI Advisor and Crisis Planner** (Groq): `services/ai/advisor/*`, `services/ai/crisis_planner/*`; frontend `AIAdvisorPanel.tsx`, `CrisisPlannerPanel.tsx`.
- [x] **Multi-tenant auth + admin user management**: `core/auth.py`, `api/endpoints/auth.py`, `admin_users.py`, `docs/AUTH.md`; migrations 0001–0003.
- [x] **Rate limiting**: slowapi, Redis-backed, 100/min global and 5/min strict (`core/rate_limit.py`).
- [x] **Watchdogs** that fail stuck collection jobs, pipeline runs, documents and search jobs, plus a dead-feed circuit breaker and revival: `celery_app.py` `beat_schedule`, `collection_tasks.py`.
- [x] **Daily pg_dump backup task** (02:00 UTC): `workers/backup_tasks.py`, `docs/BACKUP.md`.
- [x] **Prometheus `/metrics`** via `prometheus-fastapi-instrumentator` plus Celery success/failure counters in Redis: `main.py:182-196`, `core/metrics.py`, `celery_app.py` signals.
- [x] **Export Report (PDF)** for Brand Equity, Risk Center and Executive Analytics (commit `0fb3fa2`, 2026-10-14): takes one snapshot of dashboard state per click so a 45 s re-poll cannot mix data, builds a pure `ReportModel`, captures charts from a hidden stage, then renders with `jspdf` + `jspdf-autotable`, which are loaded by dynamic `import()` only on click. It embeds a Noto Sans font, draws non-Latin scripts as canvas images, states the "newest 500 articles" scope in footnotes, and disables itself with a reason when data is unavailable. Evidence: `orm_dashboard/src/components/ExportReportButton.tsx`, `ExportReportStage.tsx`, `src/lib/exportReport.ts`, `captureCharts.ts`, `reportTextImage.ts`, `src/utils/reportModel.ts` (625 lines), `reportText.ts`. Tests: `reportModel.test.ts` (50 `it`), `exportReport.test.ts` (8), `ExportReportButton.test.tsx` (6). **Not verified by me:** I did not run the export or open a generated PDF.
- [x] **Risk heatmap banding fix** (commit `3160bf9`): the severity×topic heatmap uses the same `docSeverity` rule as Risk Center and leaves never-scored documents out of every cell (`utils/riskHeatmap.ts`, `riskHeatmap.test.ts`). Also shows "N/A" for a missing reputation score.
- [x] **Dashboard**: Brand Equity, Risk Center, Competitor Compare, Executive Reputation, Executive Analytics, Intelligence Stream, Counterfeit Detection, Access Control, plus a landing page (`orm_dashboard/src/components/*`, `src/app/*`).

**Stubbed / dormant / removed (do not claim)**
- ❌ **Narrative clustering**: built, then fully removed (`bab8f3a`, `182b9c5`, `1a6467a`, 2026-09-19). A leftover `narratives` table remains in the real DB but not in `schema.sql` (`audit/closeout-report.md` [local-only]).
- ❌ **Trend detection**: removed 2026-10-01/02 (migrations `0011`, `0012`, `0013`; commit `c5b43bb`).
- ❌ **Continuous/scheduled collection**: removed in "Phase 15". `schedule_feeds` and `schedule_searches` still exist but are not on any schedule (`celery_app.py`).
- ⚠️ **Article full-text extraction**: `process_document_task(extract_article=…)` is a `pass` placeholder (`workers/document_processor.py`).
- ⚠️ **PRAW Reddit adapter** (`adapters/reddit.py`): dormant.
- ⚠️ **Document-level topic batching**: `classify_batch` is a plain for-loop and `process_batch` has no caller (`PART_F_…md` §1.2 [local-only]). Only label-level batching exists.
- ⚠️ **Language handling**: `documents.language` defaults to `"en"`; there is no language-detection library or code (grep of `app/`, `requirements.txt`). All models are English-only.
- ⚠️ **Export / reports**: PDF export now exists for 3 pages (see §4, `0fb3fa2`), but it is client-side only. There is no backend export endpoint, no CSV export, no scheduled or emailed reports (grep of `app/api` finds none). The other pages (Competitor Compare, Executive Reputation, Intelligence Stream) are not covered by the export.
- ⚠️ **Offsite backup replication**: not done (`docker-compose.yml` volume comment, `docs/BACKUP.md`).
- ⚠️ **Competitor "promote candidate" button**: documented as missing (`XOOP_FEATURE_INVENTORY_…md` [local-only]).

## 5. Hard engineering problems solved

1. **Cross-service stage isolation in a chained pipeline.** The monolithic runner (`--pool=solo`, 1 process) serialised all clients and duplicated a 1.6 GB model load. It was rewritten into a Celery `chain` of stage tasks on separate queues, each with its own FSM transition. A `link_error` handler runs exactly once and releases the Redis lock by `owner_id`. A watchdog covers dead workers because `time_limit` is a no-op under the solo pool (`aggregation_tasks.py` docstrings, `pipeline_run_watchdog`).
2. **Version-skew bug between orchestrator and stage workers.** A new `AI_SUMMARY` stage made the old orchestrator emit an illegal `NARRATIVE → REPUTATION` transition. The FSM rejected it. The fix is a deploy rule (always `docker compose up -d` unfiltered) plus `scripts/verify_deploy_services.sh` (`DEPLOY.md`).
3. **Idempotent dedup under races.** `INSERT … ON CONFLICT DO NOTHING` covers both canonical-URL and content-hash uniqueness. The same pattern is used for `sources` find-or-create (`document_service.py`, `collection_tasks.py::_get_or_create_source`). Postgres `pg_advisory_xact_lock` serialises entity promotion (`entity_discovery.py:655,855`), chosen deliberately because it is transaction-scoped and therefore safe under PgBouncer transaction pooling (`docker-compose.yml` comment).
4. **External API budget control.**
   - YouTube: atomic Redis `INCRBY` reserve-then-check against the 10,000-unit daily quota, reset on Pacific Time (not UTC), plus a 3×403/429 → 30-minute circuit breaker.
   - GDELT: Redis-shared 6 s pacing against GDELT's ~5 s/IP limit, plus one 429 retry.
   - Instagram: hard cap of 25 results per call as a cost lever.
   - Reddit/Apify: switched from the sync endpoint (HTTP 408 at 300 s) to start → poll → fetch-dataset.
   - Evidence: `adapters/youtube.py`, `gdelt.py`, `instagram.py`, `reddit_apify.py`.
5. **Dead-source handling.** A Redis consecutive-failure circuit breaker deactivates a feed after 5 connection failures. An hourly revival watchdog retries it. `source_health.reliability_penalty` grows 0.2 per failure and feeds reputation (`collection_tasks.py`).
6. **Entity-resolution precision.** Ambiguous brand names (Apple, Meta, Ford, Tesla/Nikola, Tata) are handled with context windows, negative-context rules and a per-client boost dictionary derived from entities (`matching_engine.py`, commit `40fb3bf`). Discovery candidates pass layered validators (verb filter, possessive self-reference, currency filter). Combined candidate precision rose from 45% to 65% on a 20-row manual review (`NLP_AUDIT_FIX_VERIFICATION.md` [local-only]; small sample).
7. **Cost-aware LLM use.** The LLM role gate runs only when the mechanical score is ≥ 25 (`RISK_ROLE_CLASSIFICATION_MIN_SCORE`). Failures fall back to SELF rather than suppressing risk. Summaries are cached by a content hash, because the old timestamp-keyed cache was re-billing every run (`risk_engine.py`, `ai_summary_engine.py`).
8. **Zero-shot CPU cost.** Measured ~50 s/doc, with 17 sequential forward passes per document. Label-batching was implemented and checked for equivalence against the old path (`scripts/verify_topic_batching_equivalence.py`, `PART_F`). A speedup of ~1.16× is reported in `XOOP_FEATURE_INVENTORY` [local-only]; the script is tracked but the figure is not in a tracked file.
9. **Dashboard read-through cache** (30 s TTL < 45 s poll) with explicit invalidation on alert acknowledge (`core/dashboard_cache.py`), plus identical in-flight GET de-dup in the frontend (`api.ts getCache`, per `stream_baseline.md` [local-only]).
10. **Failing loudly.** Executive-stage 100% failure no longer hides as pipeline SUCCESS (commit `f1eb9cd`). Mock sentiment/topic output is forbidden in production unless an env flag is set (`sentiment_analyzer.py`, `topic_classifier.py`). The `0012`/`0013` migrations and the schema-vs-live column diff were done with a throwaway DB (`CLAUDE.md`, `.github/workflows/tests.yml` write-path check).
11. **Schema-vs-ORM drift guard in CI**: `scripts/verify_schema_write_paths.py` builds `schema.sql` + migrations in a real Postgres and exercises the reputation/executive/benchmark upserts, because the unit tests run on SQLite (`.github/workflows/tests.yml` comment).

## 6. Existing measurable facts (only what is in the repo)

**Code size (static counts from `git ls-files`; includes tests and scripts)**
- 268 commits, 1 author (`kiran Gowda`), 2026-07-27 → 2026-10-14; 372 tracked files (`git rev-list --count HEAD`, `git ls-files`).
- ~33,800 lines of Python and ~16,500 lines of TS/TSX tracked (`git ls-files | xargs cat | wc -l`; includes tests, lockfile excluded).
- Largest backend files: `entity_discovery.py` 2,701 lines, `aggregation_tasks.py` 2,277, `sentiment_batch_processor.py` 1,146, `benchmark_engine.py` 1,099, `topic_classification_batch_processor.py` 1,077, `risk_engine.py` 966.
- DB: 37 tables, 57 `CREATE INDEX` statements in `schema.sql`, 13 migrations, a 17-topic taxonomy (`database/seed_dev.sql`, `core/risk_config.py`).
- API: ~60 route decorators in `app/api/endpoints/` (plus `/health`, `/metrics` in `main.py`).
- Workers: 10 compose services (`redis`, `backend`, `celery-worker-io/cpu/nlp/aggregation/pipeline/pipeline-2`, `celery-beat`, `frontend`).
- Queue concurrency now in `docker-compose.yml`: io 4, cpu 2, nlp 2, aggregation 3, pipeline 1 + 1 (solo). It was 3 for nlp earlier, per `PART_F` [local-only].
- Sources: 6 collector families (RSS/Google News, GDELT, HN Algolia, YouTube, Instagram, Reddit).

**Tests**
- 198 `def test_` functions across 26 `tests/test_*.py` files (static count; not executed by me).
- Frontend: 14 Vitest files and 235 `it(`/`test(` lines by static count on 2026-10-14 (up from 7 files / 150 on 2026-10-10, because of the export and heatmap commits). `stream_baseline.md` [local-only] logged "221 tests, all pass", `tsc --noEmit` exit 0 and `next build` exit 0 on 2026-10-08. That was before the export feature; I did **not** re-run the suite, so do not quote a current pass count.
- `audit/closeout-report.md` [local-only] logged "137 passed + 5 xfailed inside the image" on 2026-10-02. My grep finds 20 `xfail` mentions in tests now.
- A hand-labelled entity-matching evaluation set exists: `tests/validated_evaluation_set.json` has **292** documents with `ground_truth_labels`. I found no stored score from it.
- `tests/audit_entity_matching.py`: a hard-coded sample list of ambiguous-name sentences (Apple, Meta, Ford, Amazon…) with expected True/False. No stored result.

**Performance / quality numbers that exist (each with caveats)**
- FinBERT inference: avg 177.9 ms, p95 321 ms (n = 20); model load 15.5 s; 5.62 docs/s. `orm_collection/sentiment_audit_results/phase_f_performance.json` is **tracked**. The machine is not recorded; probably a dev machine.
- Sentiment label distribution on 177 docs: 48.6% neutral / 26.6% negative / 24.9% positive; mean confidence 0.806 (`phase_d_accuracy.json`, tracked). This is a distribution, **not accuracy**.
- Topic classification real production telemetry: avg 13–70 s/doc by day in September 2026 on a 2-vCPU droplet (`PART_F_…md` [local-only], from `documents.topic_processing_time_ms`).
- Pipeline run example: Adani run `cba2b790`, 109 new documents, 71 minutes, SUCCESS (`audit/closeout-report.md` [local-only]).
- Live client data on 2026-10-08: Adani Group 449 docs, Godrej Properties 500 (the API cap), 2 clients live (`stream_baseline.md` [local-only]).
- Image: backend image 12.7 GB → 7.62 GB after Dockerfile fix (`audit/closeout-report.md` [local-only]). The CPU-only torch change is `5c00a88` [tracked].
- Entity-candidate precision 45% → 65% (n = 20) and a 23% recall finding for an over-aggressive suppression rule (`NLP_AUDIT_FIX_VERIFICATION.md` [local-only]).

**Do NOT cite** `orm_collection/tests/validation_suite/results.json` (tracked). Queue throughput "450 tasks/s", CPU 45.2% and RAM 120 MB are **hard-coded literals** (`run_validation_suite.py:124-128`), the "10k insert" is a projected 1k mock, and `multi_client` reports `FAILED`. Quoting these would be fabricating metrics.

## 7. Metrics I should measure (cheap, this weekend)

Run every DB query read-only through the app container's own session (see `CLAUDE.md`). Run `pytest` only against a throwaway `DATABASE_URL` (see §10).

1. **Pipeline latency by stage and end to end.** `SELECT client_id, duration_s, execution_duration_s, status, started_at FROM pipeline_runs WHERE status='SUCCESS' ORDER BY started_at;` → median, p95, docs/run. Divide by new-document counts from `collection_jobs.documents_saved`. Bullet form: "median X min per N-document run".
2. **Dedup rate.** `SELECT sum(documents_found), sum(documents_saved), sum(documents_deduplicated) FROM collection_jobs;` → % duplicates suppressed. Caveat: `_stage_collect` (the Run-Pipeline path) may not write `collection_jobs`, so also compare `count(*)` against `count(distinct content_hash)` and the dedup counters in logs.
3. **Total corpus.** `SELECT document_type, count(*) FROM documents GROUP BY 1;` plus `count(*)` of `document_matches`, `risk_events`, `alerts`, `entity_mentions`, and `clients`.
4. **Matching precision/recall.** Use the 292-doc `validated_evaluation_set.json` (run `tests/entity_resolution_validation.py` or write a 20-line script). Hand-label 100 random `document_matches` rows (join `documents`) as correct or incorrect. Report precision with n and a 95% interval.
5. **Sentiment agreement.** Hand-label 100 random `document_sentiments` titles. Compute accuracy and macro-F1 vs FinBERT. Slice by source type (news vs Instagram).
6. **Topic agreement.** Same for the top-1 `document_topics` row on 100 docs; report the fraction of docs with 17/17 topics (the degenerate guard).
7. **Label-batching speedup.** Run `python orm_collection/scripts/verify_topic_batching_equivalence.py` (it prints max diffs, so also time old vs new). This makes the 1.16× figure reproducible.
8. **LLM cost and reliability.** `SELECT call_type, count(*), avg(latency_ms), avg(tokens_prompt), avg(tokens_completion), avg(success::int) FROM llm_call_log GROUP BY 1;`. Multiply tokens by the OpenRouter/Groq price. Compute cost per pipeline run. Report the cache saving by comparing summaries generated across two back-to-back runs on unchanged data.
9. **NLP cache hit rate.** In Redis: sample `nlp:*` key counts, or add a counter temporarily. Cheaper: re-run a pipeline on unchanged data and diff `topic_processing_time_ms`.
10. **Source reliability.** `SELECT status, count(*), avg(consecutive_failures) FROM source_health GROUP BY 1;` and the count of deactivated `rss_feeds`.
11. **API latency.** `curl /metrics` on the backend and read `http_request_duration_seconds` by handler (p50/p95 from histogram buckets). Compare a `X-Cache: HIT` vs `MISS` for `reputation-summary`.
12. **Test coverage.** In a throwaway Postgres: `pytest --cov=app orm_collection/tests`. Report line coverage per package (not just one number).
13. **Tenant isolation check.** Write 5 tests (or a script) that log in as a `client_user` and request another client's id → expect 403. That backs a real security claim.

## 8. Deployment and quality signals

Present
- Dockerfile is multi-stage with retrying pip install and pre-downloaded HF models (`orm_collection/Dockerfile`, commit `3fcc5d2`).
- Compose file with healthchecks on most services (the word appears 12 times; I did not count services individually) and per-service memory limits and DB pool sizes (`docker-compose.yml`).
- `DEPLOY.md` documents a deploy runbook and the version-skew incident. `scripts/verify_deploy_services.sh` exists.
- GitHub Actions `tests.yml`: pytest on Python 3.11, a real Postgres 18 schema/write-path check, and a frontend job (`tsc --noEmit`, `npm test`). **Pass/fail history is unknown to me** (`gh` is not installed here). Check the Actions tab.
- Auth, rate limiting, security headers (`core/security_headers.py`), httpOnly cookies.
- Prometheus metrics endpoint, structured logging (structlog), `llm_call_log`, per-document state-machine columns for match/topic/sentiment.
- Daily backup task. `docs/AUTH.md`, `docs/BACKUP.md`, `docs/AWS_DEPLOYMENT.md`, `docs/collection.md` (477 lines).
- Live URLs referenced in docs: `https://xoop.theaicompany.co` (frontend) and `https://api.xoop.theaicompany.co` (API), in `stream_baseline.md` and the feature inventory [local-only]. I did not verify they are up and publicly reachable; login is required.

Missing or weak
- **No root README** (`orm_dashboard/README.md` is the untouched create-next-app boilerplate).
- No Grafana/alert rules/uptime monitor in the repo; `/metrics` is exposed but nothing consumes it here.
- ESLint fails on the whole project, 268 problems (202 errors) pre-existing (`stream_baseline.md` [local-only]).
- AWS Copilot manifests and `docs/AWS_DEPLOYMENT.md` exist, but nothing shows a deployment there.
- No coverage reporting, no CD (deploy is manual `git pull` + `docker compose` over SSH).
- Backups are written to a local Docker volume only.
- Single droplet, 2 vCPU: no horizontal scaling story.

## 9. Git history summary

- 268 commits, all by one author, over ~11 weeks: Jul 2026: 1, Aug: 23, Sep: 215, Oct 1–14: 29. Busiest days: 2026-09-23 (27 commits), 2026-09-13 (24), 2026-09-06 (15). Total churn across all tracked file types: +108,470 / −34,850 lines (includes lockfiles and the 2 MB font, so it overstates code written).
- Timeline (commit hashes):
  - `b821a00` 07-27 initial commit.
  - `e030631` 08-08 "fixes before claude code".
  - `70caa1d` 08-14 drop Alembic, adopt `schema.sql`.
  - 08-25 to 08-31: matching generalisation (`40fb3bf`), entity-extraction precision rounds (`8841607`).
  - 09-03 LLM role gate (`9ade841`) and DB pool right-sizing (`73099c7`).
  - 09-05 PgBouncer + UI redesign.
  - 09-09 AI summaries (`365756d`).
  - 09-12 Instagram + Reddit adapters (`79fca6f`).
  - 09-13 brand-gate work, partly reverted (`f6ff68d`, `1b1dad1`).
  - 09-19 narrative clustering removed (`bab8f3a`).
  - 09-23 Counterfeit Detection (`80e81e5`).
  - 09-24 CPU-only torch (`5c00a88`).
  - 10-01/02 FinBERT token-limit fix (`3bdc988`), trend removal (`c5b43bb`).
  - 10-08/09 Intelligence Stream clean-up and Reddit phrase search (`0be646e`, `8a49029`).
  - 10-14 heatmap/N-A/alert-timeline fixes (`3160bf9`) and client-side PDF Export Report (`0fb3fa2`, +3,018 / −259 lines across 28 files).
- Most-touched areas by file-change count (all history): `orm_dashboard/src/components` (311), `app/services/intelligence` (160), `app/api/endpoints` (100), `orm_dashboard/src/app` (64), `src/lib` (42), `src/hooks` (42), `aggregation_tasks.py` (24), `docker-compose.yml` (17), `schema.sql` (14).
- Observation: much of September is fixes, removals and audits (a "forensics" workflow driven by `CLAUDE.md`). The history reads as an iteratively hardened production system, not a clean greenfield build.

## 10. Weaknesses and gaps an interviewer could probe (and how to answer honestly)

| Probe | Honest answer |
|---|---|
| "Is it real-time monitoring?" | No. Collection is user-triggered ("Run Pipeline"); beat only runs watchdogs/backup. The earlier continuous scheduler was deliberately removed to control metered API cost (`celery_app.py` docstring). The landing page still says "Real-time, multi-channel monitoring" (`audit/closeout-report.md`, left as is). Say "on-demand pipeline", not "real-time". |
| "How accurate is it?" | There is no end-to-end accuracy number. Sentiment is an off-the-shelf FinBERT with only a label-distribution audit; topics are zero-shot with known calibration problems (17/17 over-firing, `topic_classifier.py` comments). Entity-candidate precision was hand-checked on n = 20. Say what you measured (§7) and that you did not benchmark the models against a labelled test set. |
| "Why is it slow?" | Zero-shot costs 17 forward passes per doc on 2 vCPUs: ~13–70 s/doc and a 71-min run for 109 docs. The 3-processes-on-2-cores concurrency was sized from a benchmark whose raw numbers are not in the repo (`PART_F` §1.3). Real fixes (quantisation, GPU, document-level batching) were identified but not done. |
| "Scale?" | Two live clients (449 and 500 docs), one droplet, Postgres `max_connections=25`. The architecture supports more workers, but there is no load test. The "validation suite" numbers are hard-coded and must not be cited. |
| "Language / non-English?" | English-only models; language is hardcoded `"en"`. A Tamil Instagram post was ingested and scored by English models (`stream_baseline.md`). A known gap. |
| "Test quality?" | 198 backend tests, many with mocks and SQLite, which cannot catch Postgres constraint drift. CI adds a real-Postgres write-path check to compensate. Some tests may reach the production DB and a real LLM (from your own memory note `reference_local_tests_hit_prod_db`; I did not verify this in code, so check before running). CI status is unverified. |
| "Who built it?" | Single author, 266 commits, developed with Claude Code from about 2026-08-08 (commit `e030631` "fixes before claude code"; `CLAUDE.md`). State plainly that AI assistance was used heavily and that you can explain every design decision above. |
| "Data quality problems?" | Yes: junk executives/competitors were promoted and had to be cleaned up (Parts P/Q/R in your local notes; commit `3493d61` per your memory notes). Entity discovery precision is modest. Brand-gate fix was reverted once (`1b1dad1`). Open items remain in your memory notes. |
| "Security?" | Reasonable basics (bcrypt, revocable sessions, tenant check, rate limits). A live DB password was exposed in a chat (your memory note `project_open_items_2026_10_01`); rotate it before claiming good secret hygiene. `.env` is untracked (verified: not in `git ls-files`). |
| "Repo hygiene?" | ~50 forensic/audit docs sit at the repo root or in gitignored folders; no root README; ESLint failing; scratch files (`scratch_*.py`, `*.db`) in the working tree. |
| "Orphaned state" | A `narratives` table exists in the live DB but not in `schema.sql`; some dead code remains by design (`_stage_process`, the old scheduler tasks). |

## 11. Draft resume bullets

(Mark = needs your measurement before use.)

1. Designed and built a multi-stage, Run-Pipeline-gated Celery workflow (collect → NLP → risk → alert → AI summary → reputation → executive → benchmark → finalise) on 5 resource-isolated queues, with a per-stage state machine, atomic Redis per-client locks and watchdog recovery of stuck runs, so concurrent client runs no longer serialise through one worker. Verified in code: `aggregation_tasks.py`, `celery_app.py`. **[NEEDS NUMBER: median / p95 pipeline duration and docs per run, §7 item 1]**
2. Built ingestion adapters for 6 source families (RSS/Google News, GDELT, HN, YouTube, Instagram, Reddit via Apify) with Redis-backed quota tracking (YouTube 10k units/day, atomic reserve-then-check), a circuit breaker, shared GDELT pacing and URL + SHA-256 dedup via `ON CONFLICT DO NOTHING`, keeping external API usage inside free/paid budgets. **[NEEDS NUMBER: duplicates suppressed %, YouTube quota used/day, documents per source, §7 items 2–3]**
3. Implemented a FinBERT + zero-shot DistilBART + spaCy NLP pipeline for entity matching, sentiment and 17-topic classification, with Redis result caching, retry/state-machine failure handling and label-batched inference (equivalence-checked against the original path); moved to CPU-only PyTorch, cutting the backend image from 12.7 GB to 7.62 GB. The image sizes are from your local closeout notes, so re-check them. **[NEEDS NUMBER: precision/recall/accuracy on labelled samples; batching speedup, §7 items 4–7]**
4. Designed a weighted risk-scoring engine (topic × sentiment weights, source-reliability and reach modifiers, 25/50/75 severity bands) with an LLM role gate (SELF / BYSTANDER / EXONERATED) that only fires above a score floor and degrades safely, and cached per-item AI summaries by content hash to stop repeat billing. **[NEEDS NUMBER: LLM calls and cost per run, from `llm_call_log`, §7 item 8]**
5. Built a multi-tenant FastAPI + Next.js dashboard (8 views: reputation score, risk matrix, alerts, competitor/executive comparison, intelligence stream, counterfeit scan, admin) with cookie sessions in Redis, per-client authorisation, rate limiting and a 30 s Redis read-through cache, with a client-side PDF Export Report (snapshot-consistent, lazy-loaded jsPDF), covered by 198 backend and ~235 frontend test cases (static counts) and GitHub Actions CI with a real-Postgres schema check. **[NEEDS NUMBER: API p95 latency, line coverage, tenant-isolation test results, §7 items 11–13]**
6. Operated the platform on a DigitalOcean droplet with Docker Compose (10 services, healthchecks, PgBouncer-pooled managed Postgres), diagnosed and fixed production incidents (orchestrator/worker version skew causing an illegal FSM transition; CUDA-bloat disk exhaustion; Reddit/Apify 300 s timeout), and encoded the lessons in a deploy runbook and verification script. Only the incidents are evidenced in tracked files (`DEPLOY.md`, `CLAUDE.md`, commit `5c00a88`). **[NEEDS NUMBER: uptime or run success rate from `pipeline_runs`, §7 item 1]**

## 12. Interview questions likely, based on the actual code

1. Why did you move from continuous Celery Beat collection to a user-triggered chain? What did you trade off? (`celery_app.py`)
2. Walk me through `run_client_pipeline`. What happens if stage 4 fails? Who releases the Redis lock and how do you avoid releasing someone else's? (`_acquire_lock`, `_release_lock`, `owner_id`, error handler)
3. Explain the 2026-09-09 `NARRATIVE → REPUTATION` failure. Why did the FSM saved you, and why is "recreate everything" the rule? (`DEPLOY.md`)
4. Why is `pg_advisory_xact_lock` OK behind PgBouncer but session-level locks would not be? (`entity_discovery.py`, `docker-compose.yml` comment)
5. How does dedup work, and what happens to two different URLs with identical content? Why strip query strings entirely in `canonicalize_url`? What false merges could that cause?
6. How do you stop "Apple" the fruit or "Meta" the adjective from matching? What are the false-negative costs? (the 54.7% Tesla false-negative story in `matching_engine.py`)
7. Why zero-shot DistilBART for topics rather than a fine-tuned classifier or an LLM? What does 17 forward passes per doc cost, and what would you do about it?
8. The topic classifier fired all 17 labels on some docs. How did you diagnose and guard against it? (`e36d8ce`, the `HYPOTHESIS_TEMPLATE` revert comment)
9. FinBERT crashed with a tensor-size error on long text. What was the root cause, and why was a 1,500-character cap not enough? (`sentiment_analyzer.py`, commit `3bdc988`)
10. How does your risk score work, and why is the divisor 140? What changed when you deleted trend? (`risk_config.py`)
11. What does the SELF/BYSTANDER/EXONERATED LLM gate do, what does it do when OpenRouter is down, and how do you test it?
12. How do you keep LLM costs bounded? Why did a timestamp-keyed cache fail? (`ai_summary_engine._content_signature`)
13. How do you enforce tenant isolation? What stops a client_user from reading another client's data via `/documents/{id}`? How would you test it?
14. How do YouTube's quota reset and your circuit-breaker interact? Why Pacific Time? (`youtube.py`)
15. Why Redis for sessions rather than JWT? What happens on Redis failure?
16. SQLite unit tests vs Postgres schema: what did the CI write-path check catch, and what is still not covered?
17. How would you scale this to 100 clients? Where is the bottleneck (NLP CPU, Postgres connections, Apify cost)?
18. You removed narrative clustering and trend detection. Why, and how did you remove columns from a live DB safely? (migrations 0011–0013, archive export)
19. What is your actual accuracy? How would you evaluate sentiment, topics and entity matching, and what would you change after seeing the results?
20. In Export Report, why snapshot the dashboard state once per click, and why load jsPDF by dynamic import? How do you handle Tamil/Devanagari text that jsPDF cannot shape, and what is the cost (non-selectable text, font dependence)? (`ExportReportButton.tsx`, `reportTextImage.ts`)
21. How much of this was written with AI assistance, and how did you verify correctness? (`CLAUDE.md`'s verification sequence is a good answer.)
