# Platform-Wide Sweep: Missing Brand/Product Co-Occurrence Bug

**Date:** 2026-09-13
**Scope:** Every function that computes a client-scoped aggregate, score, or list from `Entity`/`EntityMention`/`DocumentMatch` rows. Detection pass only — verified against live DB rows, not fixed unless explicitly noted.

## Root-cause pattern (recap)

A client's own tracked-entity roster can include generic/globally-common names (person or competitor type) that were never actually mentioned alongside that client's own brand/product entity in any real document. Any engine that aggregates "every entity belonging to client X" without also requiring co-occurrence with client X's own brand/product entity in the same document will pull in unrelated coverage.

## Findings

| Engine | Has the bug? | Live contamination confirmed? | Status |
|---|---|---|---|
| `matching_engine.py` (`GlobalMatchingEngine`) | Yes — the original root cause | Yes (20 Tesla docs under Anthropic, confirmed Phase 0) | **Deferred** — platform-wide confidence-scoring retune, needs real regression testing. Not fixed today, by design. |
| `narrative_engine.py` (narrative doc-pool) | Was — excluded competitor-type only, not person-type | Yes (Tesla "Full Self-Driving" narrative) | **Fixed** (Phase 0) |
| `documents.py` (`get_client_visible_documents`, `read_documents`, `read_document`) | Was | Yes | **Fixed** (Phase 0) |
| `executive_reputation_engine.py` | Was | Yes (~20 → 7 tracked names) | **Fixed** (Phase 0 / Status Update 3) |
| `benchmark_engine.py` (`calculate_competitor_benchmarks`) | Was | Yes — 15 of 38 "competitor" entities under Anthropic had zero brand overlap (Samsung, Huawei, Apple, CrowdStrike, Volkswagen, DoorDash, IPO Filing, API, EU, Congress, Unitree Shanghai, DSpark, Microsoft Eyes, Huawei AI, OpenAI & Google) | **Fixed** (Phase 5, today) |
| `reputation_engine.py` (`calculate_reputation_score` — Sentiment, Risk, and Trend components) | Yes | **Yes, most severe finding** — 16 documents (mostly Elon Musk/Tesla news) with zero Anthropic brand co-occurrence were feeding the Sentiment component of the single most prominent number on the dashboard, "Reputation Score" (60.06) | **Fix written, compiled, NOT committed/pushed** (this task's guardrail) — see `orm_collection/app/services/intelligence/reputation_engine.py`. Code-only; takes effect on the next pipeline run, does not move today's displayed number. |
| `risk_engine.py` (`calculate_document_risk`) | Yes — groups entity mentions by `entity.client_id` with no brand-co-occurrence check at all | **Yes, confirmed live**: a "Amazon Cargo Jet Crashes... Tesla Cybercabs" article has a `RiskEvent` row under Anthropic's `client_id` | **Not fixed.** Currently **not client-facing** for Anthropic: every UI surface that shows risk (`RiskTab.tsx`, dashboard tiles) reads from the already brand-gated `documents` array via `documents.py`, not from raw `risk_events`. The write-path bug is real, but effectively contained by the downstream fixes already shipped. Flag as follow-up, same tier as `matching_engine.py`. |
| `alert_engine.py` (`evaluate_executive_alerts` etc.) | Partially — excludes `entity_type='competitor'` only, same incompleteness pre-Phase-0 `narrative_engine.py` had; inherits whatever `risk_engine.py`/`trend_detector.py` write | Checked live: Anthropic's 2 currently-active alerts (Anthropic, Claude) are both legitimately its own brand/product entities — **no currently-active contaminated alert found**. | **Not fixed.** Same-pattern gap exists in code but empirically clean right now for Anthropic. Flag as follow-up. |
| `trend_detector.py` (`detect_trends`) | Yes — queries `Entity.filter(client_id == X)` with no `entity_type` filter or brand-co-occurrence check at all | Checked live: 0 of 63 current `TrendEvent` rows for Anthropic have zero brand-doc overlap | **Not fixed.** Bug pattern present, but empirically 0 contaminated rows right now. Flag as follow-up. |
| `collection.py` (`GET /collection/status` — `total_docs`/`total_matches`/`docs_today`) | Yes — raw `Document.join(DocumentMatch).join(Entity).filter(client_id==X)` count, no brand gate | Confirmed: raw match count is 1275 documents vs. 645 that actually pass the brand gate | **Not currently client-facing.** The sidebar's "DOCS"/"ENTITIES" numbers are sourced from the already-gated `documents` array (`derivedPipelineHealth` in `dashboard/page.tsx`), not this endpoint. The only field from this endpoint actually rendered (`docs_today`) only appears in "AI Pipeline Health," which Phase 4 already gated behind `isSuperAdmin`. Flag as low-severity follow-up. |
| `intelligence.py` (`GET /{document_id}/analysis`) | Different class — a single-document access-control check (`Entity.client_id == client_id`, no `entity_type` filter), not a list/aggregate | Not a cross-entity contamination pattern in the reported sense; at most a narrow authorization edge case if a document id from another entity type is known and requested directly | Noted, not prioritized. |
| `entity_discovery.py` (candidate promotion/entity resolution) | Different class — this is the *upstream* process that first tags a co-mentioned proper noun as `entity_type='competitor'`/`'person'` without validating it's actually a real competing company or the client's own staff | Confirmed as the root of the *second* Phase 5 finding (Pentagon/Warner Music/GPT passing the brand-co-occurrence gate but not being real competitors) | Same follow-up already logged in Phase 5 — needs real classification logic, not a co-occurrence filter. |
| `sentiment_batch_processor.py`, `topic_classification_batch_processor.py` | No — these process a single document's own sentiment/topic once; they don't aggregate across a client's entity roster | N/A | Not vulnerable to this bug class. |

## Summary for follow-up scoping

Confirmed **currently client-facing today** and fixed as part of this sweep (pending your review/commit):
- `reputation_engine.py` (Sentiment/Risk/Trend components feeding "Reputation Score")

Confirmed **has the bug, not currently client-facing** (contained by already-shipped downstream fixes) — real defects, same tier as the deferred `matching_engine.py` retune, not fixed today:
- `risk_engine.py` (write path — root cause of the contaminated `RiskEvent` rows `reputation_engine.py`'s Risk component was reading)
- `alert_engine.py` (inherits from `risk_engine.py`/`trend_detector.py`; own competitor-only exclusion incomplete)
- `trend_detector.py` (write path — no gate at all, currently empirically clean)
- `collection.py` `/collection/status` (raw counts unused by any currently-visible client surface)

Separate, deeper defect (not this bug class — entity *classification* quality, not co-occurrence):
- `entity_discovery.py` candidate promotion (already logged as a Phase 5 follow-up)
- `topic_classifier.py` / zero-shot model calibration (found 2026-09-14, same tier — needs real investigation, not a co-occurrence fix): for a subset of documents (~8% of Anthropic's gated set, confirmed live on Godrej too, e.g. a real-estate listing tagged "Full Self-Driving / Autopilot" at 0.93 confidence), the BART-MNLI zero-shot classifier returns near-uniform 0.97-0.99 confidence across literally every active topic label simultaneously, rather than discriminating. A deterministic sanity guard was added same-day in `topic_classification_batch_processor.py` (when 100% of the taxonomy passes threshold for one document, treat the result as degenerate and write nothing, rather than guess which labels are real) — this stops the visible symptom (wrong topics shown to clients) but does not explain *why* the model loses discrimination on this subset of documents (informal/non-news-register text is the working guess, unconfirmed). The real fix — understanding the actual calibration failure, possibly a hypothesis-template or preprocessing issue — is unscoped follow-up work, same tier as `matching_engine.py`'s deferred retune.

No changes made to pipeline triggering, `celery-beat` scheduling, or narrative eligibility thresholds during this sweep.
