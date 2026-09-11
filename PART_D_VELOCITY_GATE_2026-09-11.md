# Narrative velocity/growth gate — implementation report

## Part 1 — What already existed (investigated before writing anything)

Confirmed live: narrative-level velocity data already exists and is already
computed by the TREND pipeline stage — nothing new needed to be built.

- `Narrative.trend_strength` ([narrative.py:19](orm_collection/app/models/narrative.py:19))
  is populated in `calculate_narratives` from a **topic-level `TrendEvent`**
  ([narrative_engine.py:1142-1149](orm_collection/app/services/intelligence/narrative_engine.py)),
  looked up by `topic_id` from a map already preloaded earlier in the same
  function (`trend_map`, `TrendEvent.trend_type == "Topic"`).
- That `TrendEvent` is produced by `TrendDetector._detect_topic_trends`
  ([trend_detector.py:511-646](orm_collection/app/services/intelligence/trend_detector.py:511)):
  a 24h-vs-7d comparison (`time_window="24h_vs_7d"`), only written when
  `abs(percent_change) >= 50.0` and the client has an established baseline
  (`baseline_established`, `system_active_days >= 2`). `trend_direction`
  ("RISING"/"FALLING") is stored directly on the row.
- This is already the exact "current-window rate vs. trailing baseline"
  design the task asked for, using the project's own existing, already-
  battle-tested 50%-move bar and 24h/7d window (used identically for
  Mention and Sentiment trends elsewhere) — not a new invented multiplier.

**Sparsity check (live query, xoop-prod, read-only):** per-cluster document
timelines are too sparse for a reliable *per-narrative* baseline (median 1
doc/narrative platform-wide, per `PART_D_NARRATIVE_VOLUME_THRESHOLD_2026-09-11.md`).
The existing gate operates at **topic** granularity (aggregated across all
of a client's documents in that topic, not just one cluster's few
documents), which is exactly why reusing it — rather than computing a new
per-narrative velocity — was the right call: topic-level volume is far less
sparse than cluster-level volume.

**Cold-start check:** worried the `percentage_change = 100.0` hardcoded
first-observation path might dominate and make the signal meaningless.
Checked live: only 11 of 165 real `Topic`-type `TrendEvent` rows (6.7%) are
that hardcode; the other 93% are genuinely computed percentage changes. Not
a concern.

## Part 2 — Gate design

Added `NARRATIVE_REQUIRE_RISING_TREND` in
[narrative_engine.py:59-91](orm_collection/app/services/intelligence/narrative_engine.py:59)
and a new gate check right after the existing source-diversity gate
([narrative_engine.py](orm_collection/app/services/intelligence/narrative_engine.py), `narrative_gated_insufficient_velocity`):

```python
if NARRATIVE_REQUIRE_RISING_TREND and (
    trend_event is None or trend_event.trend_direction != "RISING"
):
    continue
```

Three independent, complementary gates now exist before a cluster becomes a
tracked Narrative:
1. **Reach/trust + source diversity** (`NARRATIVE_MIN_ELIGIBLE_SOURCE_DIVERSITY`) — is it credible (independent corroboration)?
2. **Evidence score >= 1.0** — is there enough combined signal at all?
3. **Velocity** (new, `NARRATIVE_REQUIRE_RISING_TREND`) — is it actually growing?

**Scope decision confirmed with Kiran:** the gate excludes `EMERGING`
narratives too (no trend/risk/alert evidence yet), not just `DECLINING`
ones — a strict "credible AND growing" reading, no early-signal exception.

## Part 3 — AI-generation cost tied to the same gate

No separate change was needed: the gate is a `continue` placed before RCA
generation (`_generate_rca`) and before the `INSERT ... ON CONFLICT` write.
A narrative that fails the velocity gate never reaches RCA generation and
is never written/updated — same cost-control principle as Risk Events' AI
Summary, achieved by gate placement rather than a second check.

## Part 4 — Real before/after counts (live, read-only, xoop-prod)

| Client | Total narratives today | Trend_direction=RISING (would pass) | Removed |
|---|---|---|---|
| Tesla | 2,414 | 2,352 | 62 (2.6%) |
| Godrej Properties | 503 | 493 | 10 (2.0%) |
| Anthropic | 27 | 0 | 27 (100%) |
| Google | 4 | 0 | 4 (100%) |
| **All clients** | **2,948** | **2,845 (96.5%)** | **103 (3.5%)** |

The 103 removed break down as exactly the 65 `EMERGING` (trend_strength=0,
no `TrendEvent` at all) + 38 `DECLINING` (`trend_strength<0`) rows —
confirmed via direct status/trend_strength cross-tab.

**Honest read:** on today's data this gate barely filters the two
high-volume clients (~2-3%) and completely zeroes out the two low-volume
ones — their topics never swing >=50% day-over-day at current volume, so
`TrendDetector` never emits a `TrendEvent` for them regardless of this
change. This mirrors the same pattern already flagged for a flat
document-count threshold: a volume-sensitive gate structurally
disadvantages low-volume clients. This gate mostly matters once more
sources (Reddit, Meta) raise topic-level volume platform-wide, not as a
big filter today.

**Going-forward only, confirmed:** the gate is a `continue` inside the same
per-cluster loop the two existing gates already use — it only affects rows
a future pipeline run would insert or `ON CONFLICT DO UPDATE`. No
migration, no deletion, no schema change. Existing rows are untouched
unless/until a real pipeline run recomputes their cluster and it still
clears (or now fails) the gate.

## Safety (processing-pipeline / high-risk zone)

`narrative_engine.py` is a processing-pipeline file. This change is safe
because it:
- Adds no new query, no new external call — reuses `trend_event`, already
  fetched earlier in the same function for `trend_strength`.
- Touches no schema, no Celery routing, no other pipeline stage
  (`TrendDetector` itself is untouched).
- Is purely a new `continue` precondition, following the exact pattern of
  the two existing gates immediately above it.

## Verification run

- `pytest tests/test_narrative_engine.py` — the only test that exercises
  `calculate_narratives` end-to-end (`test_validation`) is already
  `xfail` for an unrelated, pre-existing reason (SQLite vs. Postgres
  `ON CONFLICT` upsert incompatibility) and its fixture has no `source_id`
  on any document, so it was already failing the source-diversity gate
  before this change — behavior unaffected. The three
  `_rank_prominent_persons` unit tests don't touch `calculate_narratives`
  at all. No regression from this change.

## Revision — gate flipped to exclude only DECLINING (2026-09-11, later same day)

**Why:** the original RISING-only gate structurally blocked EMERGING
narratives from ever surfacing until they became an established trend,
defeating the early-warning purpose of the feature. DECLINING (a confirmed
FALLING topic-level trend) is the one category genuinely safe to hold
back — a fading story doesn't need active surfacing.

**Change:** one-line condition flip in
[narrative_engine.py](orm_collection/app/services/intelligence/narrative_engine.py) —
`NARRATIVE_REQUIRE_RISING_TREND` now gates on
`trend_event is not None and trend_event.trend_direction == "FALLING"`
instead of the earlier `trend_event is None or trend_direction != "RISING"`.
Only the velocity-gate condition changed; the reach/trust and
source-diversity gates above it are untouched (confirmed via diff).

**Real before/after (live, read-only, xoop-prod):**

| Split | Original gate (RISING only) | New gate (excludes DECLINING only) |
|---|---|---|
| RISING (pass either way) | 2,845 (96.5%) | 2,845 (96.5%) |
| EMERGING / no trend_event | 65 — **excluded** | 65 — **now pass** |
| DECLINING (FALLING) | 38 — excluded | 38 — **still excluded** |
| **Total passing** | **2,845 (96.5%)** | **2,910 (98.7%)** |

Per client, new gate:

| Client | Total | Pass (new gate) | Excluded (DECLINING) |
|---|---|---|---|
| Tesla | 2,414 | 2,385 | 29 |
| Godrej Properties | 503 | 494 | 9 |
| Anthropic | 27 | **27** | 0 |
| Google | 4 | **4** | 0 |

**Anthropic/Google confirmation:** their earlier all-zero result is fully
reversed, not a volume artifact — every one of their narratives is
EMERGING (trend_strength=0, no TrendEvent), and EMERGING now passes
unconditionally. None of their narratives are DECLINING, so they lose
nothing under the new condition. This wasn't a case of "too low volume to
register RISING or EMERGING" — they simply never had a FALLING trend to
begin with.

**Test re-run:** `pytest tests/test_narrative_engine.py` — same result as
before this flip: 3 passed, 1 xfailed (unrelated pre-existing SQLite/
Postgres upsert incompatibility). No regression.

## Not yet done — needs your confirmation

- **Git:** nothing staged/committed. Suggested commands, for your review:
  ```bash
  git add orm_collection/app/services/intelligence/narrative_engine.py PART_D_VELOCITY_GATE_2026-09-11.md
  git commit -m "Add narrative velocity/growth eligibility gate, reusing existing topic-level TrendEvent"
  git push origin main
  ```
- **Deploy:** not run. Per `DEPLOY.md`: `git pull` on the droplet, rebuild,
  `docker compose up -d` with **no service filter**, verify `docker ps`
  all healthy, trigger one real pipeline run, confirm via direct read-only
  DB query (`narrative_gated_insufficient_velocity` log lines / new
  narrative rows). Will do this only after you confirm.
