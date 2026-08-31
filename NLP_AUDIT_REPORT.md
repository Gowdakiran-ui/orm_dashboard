# NLP Core Audit — Findings Report

**Scope:** task.md, Parts 0–5. Diagnosis only — no fixes implemented. Local-only, per instructions.

**Update — Part 1 and Part 4 fixes implemented and verified, see
`NLP_AUDIT_FIX_VERIFICATION.md` for the full before/after report. Summary:
combined entity-candidate precision 33% → 45%; narrative clustering 0 rows →
46 real rows on the same real Tesla corpus. Original findings below are
otherwise unchanged.**

## Important caveat on methodology (read this first)

Part 0 could not run as originally planned. The live DigitalOcean Postgres this
app's `.env` currently points to (`DATABASE_URL_OVERRIDE`, host
`dbaas-db-3540144-...`) has **zero rows** in `clients`, `documents`, `entities`,
`executive_candidates`, `competitor_candidates`, `document_topics`,
`document_sentiments`, and `narratives` — only 2 rows in `users`. No local
Docker Postgres was running either, so there was no mirror to fall back to.
This was flagged to Kiran directly; verbal approval was given to spin up a
**throwaway local Postgres + Redis in Docker for this session only**, which
has since been torn down (`docker rm nlp_audit_pg nlp_audit_redis`, both gone).

To keep this genuinely representative rather than fabricated, no synthetic
article text was authored. Instead: `Client.onboard_client()` (the app's real
onboarding path) provisioned a real "Tesla" client with real generated
Google News / GDELT / HN Algolia RSS feeds, and the real collection adapters
(`RSSAdapter`, `GDELTAdapter`, `HNAlgoliaAdapter`) fetched genuinely live public
news. **113 real documents were ingested; 108 matched the Tesla entity.**
Every document then ran through the actual production pipeline — entity
discovery, matching engine, topic classification (distilbart-mnli-12-3),
sentiment analysis, and narrative clustering — unmodified, with
`celery_app.conf.task_always_eager = True` so tasks ran synchronously in-process
instead of needing a worker.

**Read this as: real production code, real live news content, wrong (empty)
database until today.** It answers "how does this pipeline behave on real
data" faithfully. It does *not* tell you anything about the specific historical
candidate rows Kiran saw live before the DB went empty — those are gone. The
empty production DB is itself a separate, urgent finding — see the end of this
report.

---

## Part 1 — Entity extraction (NER) precision — **CONFIRMED broken, root cause found**

**Measured precision** (manual classification of every row in
`executive_candidates` + `competitor_candidates` for the real Tesla client,
against the real source article each came from):

| | Genuine | Total | Precision |
|---|---|---|---|
| Executive candidates | 2 | 8 | **25%** |
| Competitor candidates | 14 | 41 | **34%** |
| **Combined** | **16** | **49** | **33%** |

Two-thirds of everything a human reviewer would see in the promotion UI is junk.

**"Elon Musk Deletes Own" reproduced live, verbatim**, from real headline
*"Elon Musk Deletes Own, SpaceX and Tesla ... [X posts]"* (doc
`bbc45605-...`). Other real false positives caught in this run: "James Bond
Lotus", "Elon Musk Will Appear", "Cybercab Launch", "Frames Autonomy" (from
headline *"...Frames Autonomy?"*), "Trump Locks Down" (from *"...as Trump
Locks Down the U.S. Power Grid"*) on the executive side; "K Cybertruck",
"HK$205,000" (a price, not an org), "Cheaper Version of Model 3", "SELLAS Life
Sciences to Advance", "AMG National Trust Bank Acquires New Shares",
"Boycotting American", "the World's Largest Tesla Semi Deployment" on the
competitor side.

### Root cause — confirmed by reading the code, not inferred

`entity_discovery.py` has **two different validation regimes** for the two
entity types, and they are not symmetric:

- **`_process_person_entity`** (line 287) calls `_is_valid_person_name_layered`
  (line 611) — a real 7-layer gate (length/shape, human-name heuristics,
  action-verb filter, publisher filter, product filter, generic-org filter,
  corporate-noun filter) — **before** a candidate row is ever inserted.
- **`_process_org_entity`** (line 442) calls **no validation function at all**
  before inserting. Line 524's own comment says why: *"we create candidates
  for all ORG entities. Promotion to verified competitor happens later based
  on thresholds."* `_is_valid_org_name_layered` (line 973) — the equivalent
  7-layer gate for orgs — exists and is real, but it is only ever called from
  the **promotion** path (line 1277), never from candidate creation. This is
  a deliberate, documented design choice (see the comment at line 862: *"this
  runs at candidate creation, not on update... those are re-gated by
  `_is_valid_org_name_layered()` at promotion time instead"*) — not an
  oversight in that file. But it means the raw `competitor_candidates` table
  (34% precision, measured above) is **unfiltered by design**, while the
  `executive_candidates` table (25% precision, measured above) already runs
  through a real filter and is *still* only 25% precise.

That second number is the more urgent one: the person-side filter already
exists and is still letting through headline fragments like "Elon Musk Deletes
Own" and "Trump Locks Down". Looking at why: `_is_valid_person_name_layered`'s
Layer 3 (Action Phrase Filter) is a **hardcoded denylist** of ~25 words (buy,
sell, invest, watch, drive, ...). "Deletes", "Locks", "Appear", "Frames" are
verbs but aren't on that list, so a 3-4 word capitalized headline span with an
unlisted verb sails through every layer — none of the 7 layers do real
part-of-speech/grammatical checking, they're all denylists over specific
words. This matches task.md's hypothesis exactly: *the extractor pulls
capitalized phrase spans without checking they're a coherent noun phrase*, and
it is a missing post-filter, not a spaCy model limitation — spaCy's own
`en_core_web_sm` doesn't expose confidence scores at all (confirmed separately
in `orm_collection/scratch/phase1_audit/audit_core1_entity_extractor.py`,
Test E), so there's no numeric score to threshold on; grammatical shape
(does the phrase contain a finite verb / is it a valid NP) is the only signal
available and today it's checked with an incomplete word list, not real POS
tagging.

### Proposed fix (not implemented — needs sign-off, per task.md)

1. **Symmetry first, cheapest fix**: call `_is_valid_org_name_layered` from
   `_process_org_entity` before insertion too, same as the person path already
   does. This is a policy question, not a code-complexity one — the
   comment at line 862 states the current asymmetry was a deliberate choice
   (candidates stay a permissive discovery pool; promotion is the real gate).
   Flipping it changes what the promotion UI shows reviewers, which is exactly
   what task.md's originating complaint was about. **Needs Kiran's decision**,
   not just an engineering call.
2. **Real grammatical filtering, not a bigger denylist.** spaCy's own POS
   tagger (already loaded as part of `en_core_web_sm`, unused for this
   purpose today) can check whether a NER span contains a token tagged `VERB`
   in a finite form — this replaces the hand-maintained action-verb denylist
   (Layer 3) with a real structural check and would have caught "Deletes",
   "Locks", "Appear", "Frames" without needing those specific words added by
   hand. Low risk: purely additive to the existing layer stack, same spaCy
   model already in memory, no new dependency.
3. Do **not** retrain or replace the NER model — task.md's own framing was
   right, this is a missing post-filter problem, confirmed by the fact that
   the filter that already exists (person side) is still the same shape of
   bug (denylist gaps), not a spaCy accuracy ceiling.

---

## Part 2 — Topic classification — over-triggering confirmed at scale, recall looks fine

**Recall:** 0/108 real documents got zero topics assigned (no recall gap by
that measure — every document matched at least one of the 17 seeded topics).

**Precision / over-triggering — measured across all 108 documents, not just a
sample:**

| Topic | Docs hit | % of corpus |
|---|---|---|
| Electric Vehicles | 103 | 95% |
| Autonomous Driving | 82 | 76% |
| Innovation | 79 | 73% |
| Competition | 54 | 50% |

Average **5 topics assigned per document**, several documents got 10-13
simultaneously (multi-label zero-shot with independent per-label entailment
scores, confirmed in `audit_core3_topic_classifier.py` Test H — scores are not
softmax-normalized, so many labels legitimately exceed 0.5 at once). 76% of
*all* Tesla documents getting "Autonomous Driving" is not plausible as a true
positive rate — spot-checking real titles that got it: *"5 Things You Should
Know About Driving the Tesla Model Y L Premium"* (0.94), *"Tesla Model Y vs
BMW iX1 vs others: Which EV for chauffeur driving?"* (0.89) — these are
test-drive/comparison pieces about human-operated driving, not self-driving
technology. The likely mechanism: the zero-shot label string **"Autonomous
Driving"** shares the token "driving" with ordinary "test drove"/"driving
experience" article text, and distilbart's entailment scoring is picking up
that lexical overlap rather than the semantic distinction between
"a human driving a car" and "a car driving itself." This is a genuine
precision problem worth a fix, separate from Part 1's — it's a label-wording
sensitivity issue in a zero-shot classifier, not a missing filter.

**Taxonomy adequacy:** all 17 topics fired at least once across the corpus
(Labor Relations rarest at 2%, Electric Vehicles most common at 95%) — no
recurring off-taxonomy subject was visible in this sample. The 17-label set
looks adequate for Tesla's real content mix; the problem is precision within
existing labels, not missing labels.

---

## Part 3 — Sentiment analyzer — neutral-bias confirmed, near-zero positive detection

**Full distribution, all 108 real documents** (label was computed against a
fixed `{"positive": 1.0, "neutral": 0.0, "negative": -1.0}` map — `score` is a
directional sign, not a magnitude; `confidence_score` carries the real
continuous value and is well-distributed, 0.49–1.00, so the analyzer itself is
not degenerate):

| Label | Count | % |
|---|---|---|
| Neutral | 92 | **85%** |
| Negative | 14 | 13% |
| Positive | **2** | **1.9%** |

Spot-checking real headlines the model called Neutral that a human read would
likely call mildly positive: *"$35,000 Tesla Model 3 Available Now"*,
*"Optimus Just Entered Production at Fremont"*, *"Tesla Model 3 Gets More
Range in Europe Thanks to Just One Improvement"*. This is the **opposite**
bias from what task.md flagged as the risk to check for (over-triggering
negative on ordinary business news) — here it's the model almost never
calling anything positive at all, collapsing routine positive product/business
news into Neutral. Worth a targeted look at `sentiment_accuracy_enhancer.py`'s
calibration rules (the ORM rule layer sitting on top of FinBERT) for whether
POS_WORDS coverage is much thinner than NEG_WORDS coverage — not confirmed
here, flagged for the next pass since task.md scoped this part as a spot-check,
not a full root-cause dig.

---

## Part 4 — Narrative clustering — **CONFIRMED: log lies, zero narratives written**

Ran `NarrativeEngine().calculate_narratives()` live against the real Tesla
client with topics fixed and 108 real documents present. Result:

- **0 rows in `narratives`** — verified directly via `SELECT COUNT(*) FROM
  narratives` after the run.
- The log still emitted `narrative_calculation_complete` with a clean latency
  number, exactly as task.md's Bug A predicted — **the log does not prove
  anything was written.**
- Every single candidate cluster was rejected at
  `narrative_gated_insufficient_evidence` (confirmed via the real run's own
  log lines, not inferred).

**Root cause, traced live:**

1. Clustering (`narrative_engine.py` ~line 428) groups documents within the
   same topic by **Jaccard similarity of title tokens** (≥0.25 overlap) inside
   a 3-day window. Real news headlines about the same underlying event, written
   by different outlets, rarely share 25% of their significant words verbatim
   — so almost every document became its own **singleton cluster** in this
   real run.
2. The evidence gate (line 219): `evidence_score = doc_count*0.4 +
   source_diversity*0.2`, `+1.5` if a trend/risk/alert event co-occurs, and the
   gate requires `evidence_score >= 1.0` (line 532). A singleton cluster
   scores exactly `0.4 + 0.2 = 0.6` — confirmed, every rejected cluster in the
   real log showed `score=0.6`. Without a trend/risk/alert co-signal (none
   were computed in this run — those are separate aggregation tasks not run
   here), a cluster needs **≥2 real documents plus source diversity** just to
   clear 1.0, and title-Jaccard clustering essentially never produces that for
   real headline text.

This is a compounding pair of bugs, not one: the clustering key is too strict
for real-world headline diversity, *and* the evidence gate has no path to pass
without either multi-document clustering (which the first bug prevents) or an
upstream trend/risk/alert signal. Task.md's ask — "check whether clusters that
DO form are coherent" — couldn't be evaluated because **no clusters formed at
all** on this real 108-document corpus.

**Not proposing a fix here** (task.md scope is diagnosis-first) but flagging
the two candidate angles for sign-off: (a) loosen clustering — entity-overlap
or embedding-similarity instead of raw title-token Jaccard, which is far more
robust to real headline paraphrasing; (b) loosen the gate for
`doc_count >= 2` clusters specifically, since two independent outlets covering
the same real event is itself real corroborating evidence, comparable in
spirit to the `+1.5` trend/risk/alert bonuses already in the formula.

---

## Part 5 — Error handling & capacity (light pass, per task.md's own instruction not to over-invest)

**Error isolation:** `TopicClassificationBatchProcessor`
(`topic_classification_batch_processor.py` ~line 558) and
`HardenedSentimentProcessor` (`sentiment_batch_processor.py` ~line 780/820)
both wrap **per-document** model inference in try/except, log the full
exception type + stack trace + elapsed time, roll back only that document's
transaction, and return a structured failure result rather than raising — a
malformed/empty document cannot crash the batch or corrupt sibling documents'
results. Grepped for bare `except: pass` across
`app/workers/` and `app/services/intelligence/` — the only bare
`except Exception: pass` found (line 562 in the topic processor) is a
secondary rollback-inside-an-except-handler, itself already inside an outer
except that logs the real failure first — not a silent-swallow of a primary
error. No other bare-except-pass patterns found in the NLP-touching code
paths. This looks solid; no live-verified defect found here (Phase 1/23 of
`TASK.md` already activated the previously-dead in-process retry machinery for
both processors, per `FINDINGS.md`).

**Latency, measured live on this run** (real per-stage timings from the
actual 113-document collection + intelligence pass, not the old 89-doc/70-min
number — this run is a fresher, smaller-scale but directly comparable
data point):

- `entity_matching`: ~30–50ms/doc
- `topic_classification`: **~3.8–5.8s/doc** — clearly the dominant cost
- `sentiment_analysis`: ~200–220ms/doc
- `total_document_intelligence`: ~4.2–5.8s/doc

Topic classification (the zero-shot BART model) is 15-20x the cost of
sentiment analysis per document and is the latency bottleneck by a wide
margin. Nothing here suggests a regression versus the earlier 89-doc/70-min
figure (that works out to ~47s/doc under load-test conditions including
queueing; this run's ~4-6s/doc is unqueued single-process throughput, so
the two numbers aren't directly comparable, but neither points to a new
problem). Per task.md's instruction, not re-running a full capacity test.

---

## Prioritized fix list (diagnosis complete, nothing implemented)

1. **Entity extraction precision (Part 1)** — highest impact, directly
   confirmed as the cause of the promotion-UI bug. Two independent, small
   fixes: (a) decide whether org candidates should get the same pre-insert
   gate person candidates already have (policy call), (b) add real POS-based
   verb detection to replace the hardcoded action-verb denylist on **both**
   entity types — this alone would have caught every fragment example cited
   in task.md.
2. **Narrative clustering + gating (Part 4)** — currently produces **zero**
   output on real data; the misleading "complete" log makes this invisible
   without a live check like the one done here. High severity because it's a
   total feature failure, not a precision/recall shortfall.
3. **Sentiment neutral-bias (Part 3)** — worth a calibration-rule audit
   (POS_WORDS vs NEG_WORDS coverage) — likely a moderate, contained fix once
   root-caused.
4. **Topic over-triggering on "Autonomous Driving" (Part 2)** — label-wording
   sensitivity in the zero-shot classifier; lowest urgency of the four since
   recall is fine and this is a precision/UX issue, not a missing-data one.

## Separate, urgent, out-of-scope finding

**The live production database this app currently connects to is empty**
(0 rows across every core content table). This was not part of task.md's
scope and nothing here investigates or fixes it — flagging because it's
blocking, unrelated to the NLP pipeline itself, and time-sensitive.

---

*No code was changed. No commits or pushes were made. The throwaway local
Postgres (`nlp_audit_pg`) and Redis (`nlp_audit_redis`) Docker containers used
to generate this report's real data have been stopped and removed. Raw
exported candidate/document/topic/sentiment JSON used for this analysis is at
`orm_collection/scratch/nlp_audit_out/` (gitignored, local only).*
