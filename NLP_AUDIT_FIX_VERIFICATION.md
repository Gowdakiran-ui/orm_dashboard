# NLP Audit Fixes — Verification Report (Part 1 + Part 4)

Implements and verifies the fixes for `NLP_AUDIT_REPORT.md` Part 1 (entity
extraction precision) and Part 4 (narrative clustering producing zero output).
Local only. No code was staged, committed, or pushed — see the end of this
file for the exact commands to run.

## Methodology, same as the original audit

Throwaway local Postgres (`nlp_fix2_pg`, later renamed across a couple of
throwaway containers as the DB was reset for a clean test) + Redis
(`nlp_fix2_redis`), both **stopped and removed** after verification —
confirmed via `docker ps -a` returning empty. Real Tesla client onboarded
through the app's own `onboard_client()`, real news collected from the real
Google News / GDELT / HN Algolia feeds it generates, full real pipeline run
with `task_always_eager=True`. Same technique as the original report, run
fresh against the fixed code. Never touched the live Droplet or its database.

**A methodology correction, found while verifying Fix B, disclosed here
rather than glossed over**: my first direct-invocation test script for
`NarrativeEngine().calculate_narratives()` never called `db.commit()`
afterward, so any narrative written to the nested savepoint got rolled back
on `db.close()`. I re-checked whether this affected the *original* audit's
"0 narratives" finding — it didn't materially change the conclusion:
the original run's own log showed **100% of ~390 candidate clusters**
rejected at `narrative_gated_insufficient_evidence, score=0.6`, meaning
execution never reached the insert code path at all in that run, commit bug
or not. But it's a real gap in that verification step's rigor, and I want to
be upfront about it rather than let it stand uncorrected. All numbers in this
report were produced with the commit bug fixed and independently confirmed
via direct `SELECT` against the throwaway DB.

---

## FIX A — Entity extraction precision

### What changed

1. **`_process_org_entity` now validates before inserting**, mirroring
   `_process_person_entity`'s existing pattern. Previously it inserted every
   ORG-labeled NER span unfiltered by design (see the removed comment: *"we
   create candidates for all ORG entities... re-gated at promotion time
   instead"*). It now calls the same `_is_valid_org_name_layered` gate that
   `promote_competitor_candidates` already used, before a row is ever
   created. `process_document` now computes `self_reference_terms` and
   `source_terms` once per document (not per entity) and threads them
   through, matching the existing per-batch-not-per-candidate reuse
   discipline documented elsewhere in this file.
2. **New POS-based verb detection** (`_span_verb_token`), replacing the old
   hardcoded action-verb word list (Layer 3 of
   `_is_valid_person_name_layered`) and added as a new layer (Layer O1c) to
   `_is_valid_org_name_layered`. Runs the already-loaded spaCy pipeline over
   the candidate span and rejects it if any token is tagged `pos_ == "VERB"`.
   Deliberately excludes `pos_ == "AUX"` — verified live against "Will
   Smith"/"May Wong" (real first names spaCy tags as AUX in a short span) to
   avoid false rejections.

### Honest limitation, verified live, not glossed over

spaCy's tagger loses accuracy on a 2-4 word span taken out of its sentence
context. Tested directly:

| Span | spaCy tag (isolated) | Caught? |
|---|---|---|
| "Elon Musk **Deletes** Own" | Deletes → VERB/VBZ | **Yes** |
| "Elon Musk Will **Appear**" | Appear → VERB/VB | **Yes** |
| "**Boycotting** American" | Boycotting → VERB/VBG | **Yes** |
| "**Trump Locks** Down" | Locks → PROPN (not VERB) | **No** |
| "**Frames** Autonomy" | Frames → PROPN (not VERB) | **No** |

"Trump Locks Down" and "Frames Autonomy" still get through — spaCy's tagger,
given only the 2-3 word fragment with no surrounding sentence, tags "Locks"
and "Frames" as proper nouns (capitalized, sentence-initial-looking), not
verbs. This is documented in the new `_span_verb_token` docstring in the code
itself, not just here.

### Verification — real data, before/after, same methodology

Re-ran the exact same real-Tesla-corpus pipeline used for the original audit
(113 documents collected, 108-109 matched to Tesla depending on the exact
live news pulled that minute — feeds are live and change between runs).
Manually classified every row in `executive_candidates` +
`competitor_candidates` as genuine or a parsing error, same as the original
audit.

| | Genuine | Total | Precision | Baseline |
|---|---|---|---|---|
| Executive candidates | 2 | 8 | **25%** | 25% (unchanged) |
| Competitor candidates | 11 | 21 | **52%** | 34% |
| **Combined** | **13** | **29** | **45%** | **33%** |

Competitor candidate *count* dropped from 41 (baseline) to 21 — the pre-insert
gate is filtering roughly half of what used to reach the table at all, before
precision is even measured. Executive precision is unchanged on *this specific
run* because the two remaining false positives ("Trump Locks Down", "Frames
Autonomy") are exactly the documented context-free-span limitation above —
confirmed directly via `_span_verb_token`, not assumed.

**Directly confirmed via live log lines** (real rejections during this run,
not constructed):

```
competitor_candidate_rejected_at_creation candidate='Boycotting American' ... layer='Layer O1c — Verb Filter' reason="Contains a verb: 'Boycotting'"
competitor_candidate_rejected_at_creation candidate='Capital Budget Skyrocketed' ... layer='Layer O1c — Verb Filter' reason="Contains a verb: 'Skyrocketed'"
competitor_candidate_rejected_at_creation candidate='Tesla Stock Has' ... layer='Layer O1c — Verb Filter' reason="Contains a verb: 'Has'"
competitor_candidate_rejected_at_creation candidate='Tesla Stock Could Benefit' ... layer='Layer O1c — Verb Filter' reason="Contains a verb: 'Benefit'"
executive_candidate_rejected candidate='Elon Musk Will Appear' ... layer='Layer 3 — Verb Filter' reason="Contains a verb: 'Appear'"
executive_candidate_rejected candidate='Elon Musk Deletes Own' ... layer='Layer 3 — Verb Filter' reason="Contains a verb: 'Deletes'"
```

**Task's explicit examples, checked one by one:**
- "Elon Musk Deletes Own" — **confirmed gone**, rejected at creation, never
  appears in `executive_candidates` in the fixed run (it did in the baseline).
- "Trump Locks Down" — **still present**, per the documented spaCy-context
  limitation above.
- "K Cybertruck" — **still present**. Not a verb phrase, so the verb layer
  correctly doesn't touch it; it slips through because Tesla's own products
  ("Cybertruck", "FSD", "Autopilot", "RWD") are still not registered as
  `entity_type='product'` rows in this dataset — a pre-existing, separately
  documented gap in `_client_self_reference_terms` (*"there are currently
  zero entity_type='product' rows... this branch is inert today"*), not
  something Fix A's scope (wiring + verb detection) touches.
- "HK\$205,000" — **still present**, same reason: a price string isn't a
  verb, self-reference term, publisher, or market/regulator term, so no
  existing layer catches it. Out of Fix A's stated scope.

### Residual gap found, not fixed (flagging, not touching)

`"Tesla's Autopilot"` (curly apostrophe) still gets created as a competitor
candidate. Traced why: `_is_valid_org_name_layered`'s Layer O2 self-reference
check does `normalized_lower.startswith(term + " ")`, which requires the
self-reference term to be immediately followed by a space — but
`_normalize_name()` doesn't strip a possessive `'s` from the *start* of a
multi-word name (it only strips corporate suffixes at the *end*), so
`"tesla's autopilot"` never starts with `"tesla "` (note the missing
apostrophe-s). This is a distinct bug from anything in scope here — flagging
for a separate fix, not touched in this change.

---

## FIX B — Narrative clustering

### What changed

1. **Entity-overlap clustering**, supplementing (not replacing) the existing
   title-token Jaccard check. Two documents in the same topic/time-window can
   now cluster if they share any matched entity **other than the client's own
   brand entity** (excluded deliberately — every document in a client's
   corpus mentions the brand by construction, so including it would collapse
   an entire topic into one mega-cluster instead of distinguishing real
   events).
2. **Multi-document evidence bonus**: `_calculate_confidence_and_gate` now
   adds `+1.0` to `evidence_score` whenever a cluster has `doc_count >= 2`,
   in the same spirit as the existing `+1.5` trend/risk/alert bonuses — real
   corroboration from independent clustering (title similarity or shared
   entities) is itself evidence. Singleton clusters are deliberately left
   untouched (`evidence_score` stays 0.6, still correctly gated) — verified
   directly:

```
singleton (doc_count=1, source_diversity=1): 0.6
2-doc, 1 source (the reported gap, previously exactly 1.0):        2.0
2-doc, 0 source_diversity:                                          1.8
3-doc, 2 sources:                                                    2.6
```

### Verification — real data, before/after

Ran `NarrativeEngine().calculate_narratives()` against the same real,
freshly-collected 109-document Tesla corpus used for Fix A's verification
(same run, same client, same real news).

| | Narratives written | 
|---|---|
| Baseline (original audit) | **0** |
| After fix | **46** |

Confirmed via direct `SELECT COUNT(*) FROM narratives`, not the log line
alone (the whole point of the original finding was that the log lies).

### Coherence spot-check, real clusters, real documents

Pulled `evidence_metadata.supporting_documents` for three real clusters and
looked at the actual titles:

**"Tesla Cybercab to launch Sept. 3..." (3 documents, all genuinely about the
same event):**
- *Tesla Cybercab to launch Sept. 3 as robotaxi bet ramps up* — Yahoo Finance
- *Tesla and Uber Won Robotaxi Permits—Why Citizens Kept Both Ratings
  Unchanged* — Yahoo Finance
- *My Tesla Cybercab launch predictions* — Electrek

Three different outlets, three different headlines with near-zero literal
word overlap, all genuinely about Tesla's Cybercab robotaxi launch. This is
exactly the real-world case task.md's Part 4 asked to check and the case the
old title-Jaccard-only clustering structurally couldn't catch.

**"AMG National Trust Bank Acquires New Shares..." (10 documents):**
All 10 are MarketBeat's formulaic "\[Fund\] \[Acquires/Purchased/Invested\]
Shares in Tesla, Inc. \$TSLA" articles, published within 2 hours of each
other on the same day — a real, recurring pattern (MarketBeat publishes many
near-identical 13F-filing-disclosure articles same-day). Genuinely coherent
as a themed cluster, even though it's a recurring content pattern rather than
a single discrete news event — a legitimate real narrative theme.

**"Tesla Model Y RWD real world range tested..." (2 documents):**
- *Tesla Model Y RWD real world range tested, explained* — Autocar India
- *Tesla Model Y India sales cross 600 units with 115 delivered in July* —
  Autocar India

Same publisher, same general subject (Tesla Model Y in the Indian market),
3 days apart — reasonably coherent, though this is a looser "same beat"
relationship rather than the same discrete event, worth knowing as the
softer end of what counts as a "narrative" under the current definition.

No incoherent cluster (documents merged that share nothing but noise) was
found in the sample checked.

---

## Files changed

- `orm_collection/app/services/intelligence/entity_discovery.py`
- `orm_collection/app/services/intelligence/narrative_engine.py`

No other files touched. No schema changes. No `.env`/config changes.

## Git commands (not run — for Kiran to execute)

```bash
git add orm_collection/app/services/intelligence/entity_discovery.py orm_collection/app/services/intelligence/narrative_engine.py NLP_AUDIT_REPORT.md NLP_AUDIT_FIX_VERIFICATION.md
git commit -m "Fix entity-candidate precision (pre-insert org validation + POS verb filter) and narrative clustering (entity-overlap + multi-doc evidence bonus)"
```

Not pushed — per instructions, this stays local until you decide to deploy.
