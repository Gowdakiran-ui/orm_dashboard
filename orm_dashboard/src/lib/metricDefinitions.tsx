import React from "react";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";

/**
 * Single source of truth for every static "what does this number mean"
 * definition surfaced via InfoTooltip across the dashboard (Tier 1 of the
 * explainability work). Each constant is rendered wherever that metric
 * appears so the wording never has to be duplicated or drift between
 * screens. Tier 3 will replace these with dynamic, per-metric content —
 * this file only needs to change shape then, not the call sites that
 * reference it.
 *
 * Every number below is copied from the backend code that actually
 * computes it, not estimated:
 *   - Risk severity bands: orm_collection/app/core/risk_config.py
 *     RISK_THRESHOLDS (mirrored on the frontend as
 *     src/utils/riskLevel.ts, imported here so these two can't drift).
 *   - Reputation grade cutoffs: orm_collection/app/services/intelligence/
 *     reputation_engine.py ReputationEngine._determine_grade (same scale
 *     used by ExecutiveReputationEngine).
 *   - Risk category names: orm_collection/app/core/risk_config.py
 *     TOPIC_WEIGHTS keys (the actual topic taxonomy risk_engine.py scores
 *     against — nothing here is invented).
 *   - Sentiment scale: orm_collection/app/services/intelligence/
 *     sentiment_analyzer.py score_map (positive=1.0, neutral=0.0,
 *     negative=-1.0).
 *   - Risk Matrix axes / Average Risk Score: traced directly from the
 *     frontend code that builds each chart (see per-constant notes below).
 */

const LOW_MAX = RISK_THRESHOLDS.LOW_TO_MEDIUM;
const MED_MAX = RISK_THRESHOLDS.MEDIUM_TO_HIGH;
const HIGH_MAX = RISK_THRESHOLDS.HIGH_TO_CRITICAL;

export function RiskSeverityDefinition() {
  return (
    <>
      <span className="block font-bold">Risk Severity</span>
      <span className="block">
        Each item&apos;s Risk Score (0–100) is bucketed into a severity band:
      </span>
      <span className="mt-1 block">
        <b>Low</b> (0–{LOW_MAX}) — routine coverage, no action needed.
      </span>
      <span className="block">
        <b>Medium</b> ({LOW_MAX + 1}–{MED_MAX}) — worth monitoring.
      </span>
      <span className="block">
        <b>High</b> ({MED_MAX + 1}–{HIGH_MAX}) — warrants review.
      </span>
      <span className="block">
        <b>Critical</b> ({HIGH_MAX + 1}–100) — needs immediate attention.
      </span>
    </>
  );
}

export function ReputationGradeDefinition() {
  return (
    <>
      <span className="block font-bold">Reputation Grade</span>
      <span className="block">The Reputation Score (0–100) maps to a letter grade:</span>
      <span className="mt-1 block"><b>A+</b> 90–100 &nbsp; <b>A</b> 80–89.9</span>
      <span className="block"><b>B</b> 70–79.9 &nbsp; <b>C</b> 60–69.9</span>
      <span className="block"><b>D</b> 40–59.9 &nbsp; <b>F</b> below 40</span>
    </>
  );
}

export function ReputationScoreDefinition() {
  return (
    <>
      <span className="block font-bold">Reputation Score</span>
      <span className="block">
        A 0–100 score blending sentiment (30%), risk (30%), narrative
        exposure (15%), coverage trend (10%), source reliability (10%) and
        media visibility (5%) over a rolling window, weighted by how much
        signal is actually available for each part.
      </span>
    </>
  );
}

/**
 * Shared by both Risk Center matrices — RiskAnalyticsPanel.tsx's "SOC Risk
 * Matrix" and RiskTab.tsx's "Risk Matrix (Likelihood × Impact)" card. They
 * used to disagree (SOC Risk Matrix derived Likelihood from sentiment
 * negativity, an invented formula RiskTab.tsx's own code comment already
 * called "fabricated" and had moved away from); useAnalytics.ts's
 * riskMatrixData now computes Likelihood the same way RiskTab.tsx does, so
 * one definition covers both.
 *
 * Likelihood = risk_engine.py's explainability.confidence, i.e.
 * (topic_conf + entity_sentiment_conf) / 2 — verified directly against
 * risk_engine.py lines ~621-726. That is a measure of how strong the
 * underlying topic/sentiment signal was, not a probability of the risk
 * occurring or recurring: nothing in this system tracks risk-outcome or
 * recurrence data. (Note: this is a different signal from this platform's
 * SELF/BYSTANDER/EXONERATED role classification, which is a separate,
 * later gate on final_score and does not feed into this confidence value —
 * checked against source, the two are not the same mechanism.)
 */
export function RiskMatrixAxesDefinition() {
  return (
    <>
      <span className="block font-bold">Risk Matrix: Impact × Likelihood</span>
      <span className="block">
        <b>Impact</b> is the item&apos;s computed Risk Score (0–100) — the same
        topic + sentiment + coverage-trend score, adjusted for source
        reliability, that drives its severity band above.
      </span>
      <span className="mt-1 block">
        <b>Likelihood</b> is how confident the system is that this is a
        genuine risk (0–100) — based on the strength of the underlying topic
        and sentiment detection. It is not a prediction that the risk will
        happen or recur; low Likelihood means the score rests on thinner
        evidence, not that the risk is unlikely.
      </span>
    </>
  );
}

export function AverageRiskScoreFeedDefinition() {
  return (
    <>
      <span className="block font-bold">Average Risk Score</span>
      <span className="block">
        The mean Risk Score (0–100) across every document currently in this
        client&apos;s monitored feed — including documents that scored 0 risk.
        This is a feed-wide average, not tied to any single narrative.
      </span>
    </>
  );
}

export function AverageRiskScoreTrackedDefinition() {
  return (
    <>
      <span className="block font-bold">Average Risk Score</span>
      <span className="block">
        The mean Risk Score (0–100) across only the documents counted as a
        tracked risk here — those scoring above {LOW_MAX} (Medium severity or
        higher). Routine, near-zero-risk coverage is excluded so this
        doesn&apos;t get diluted by noise. This is a feed-wide average across
        this client&apos;s tracked risks, not tied to any single narrative.
      </span>
    </>
  );
}

export function RiskCategoriesDefinition() {
  return (
    <>
      <span className="block font-bold">Risk Category</span>
      <span className="block">
        The topic detected in a document that most drives its risk score.
        Categories are ranked by inherent severity: General News, Partnership
        and Funding score lowest; Executive Changes, Customer/Employee
        Complaints and Layoffs are mid-severity; Cybersecurity, Data Breach,
        Legal, Fraud and Regulatory Action score highest.
      </span>
    </>
  );
}

export function SentimentScaleDefinition() {
  return (
    <>
      <span className="block font-bold">Sentiment Score</span>
      <span className="block">
        Runs from -1.0 (most negative coverage) to +1.0 (most positive), with
        0.0 neutral. Positive articles score +1.0, neutral articles 0.0, and
        negative articles -1.0 per document before any averaging.
      </span>
    </>
  );
}

/**
 * Competitor Compare radar chart (CompetitorsTab.tsx singleCompetitorRadarData)
 * and its Reputation Compare / Share of Voice bar charts below it. Each axis
 * value verified directly against the source that computes it:
 *   - Reputation Score: same 0-100 blended score as ReputationScoreDefinition
 *     above (client via ReputationEngine; competitor via BenchmarkEngine's
 *     reputation_score field).
 *   - Sentiment Score: the -1..+1 average from sentiment_analyzer.py,
 *     normalized to 0-100 for this chart -- client already 0-100 via
 *     ReputationEngine's ((avg+1)/2)*100, competitor via the same (x+1)*50
 *     mapping applied client-side (CompetitorsTab.tsx singleCompetitorRadarData).
 *   - Risk Containment: 100 minus the entity's average Risk Score (0-100,
 *     same risk_engine.py score as Risk Severity above) -- a frontend-only
 *     inversion so "higher is better" holds for every radar axis; it is not
 *     a distinct backend metric of its own.
 *   - Share of Voice: benchmark_engine.py's calculate_competitor_benchmarks --
 *     a competitor's SOV = its mention count / (client + every tracked
 *     competitor's mention count) x 100 over the same rolling window the
 *     rest of the benchmark run uses. The client's own SOV (no benchmark row
 *     of its own) is 100 minus the sum of every tracked competitor's SOV
 *     (utils/shareOfVoice.ts calculateClientSOV), floored at 0.
 */
export function CompetitorRadarAxesDefinition() {
  return (
    <>
      <span className="block font-bold">Competitor Comparison Metrics</span>
      <span className="block">
        <b>Reputation Score</b> (0–100) — the same blended reputation score
        used everywhere else in this dashboard.
      </span>
      <span className="mt-1 block">
        <b>Sentiment Score</b> — average coverage tone, normalized from the
        -1.0..+1.0 scale to 0–100 for this chart (50 = neutral).
      </span>
      <span className="mt-1 block">
        <b>Risk Containment</b> — 100 minus the entity&apos;s average Risk
        Score, so a higher bar always means lower risk exposure.
      </span>
      <span className="mt-1 block">
        <b>Share of Voice</b> — this entity&apos;s share of total tracked
        mentions (itself vs. client + every tracked competitor), as a
        percentage.
      </span>
    </>
  );
}

export function ShareOfVoiceDefinition() {
  return (
    <>
      <span className="block font-bold">Share of Voice (SOV)</span>
      <span className="block">
        A competitor&apos;s share of total tracked mentions: its mention
        count divided by (client + every tracked competitor&apos;s mention
        count), as a percentage. The client&apos;s own SOV is 100 minus the
        sum of every tracked competitor&apos;s SOV, floored at 0 — it has no
        benchmark row of its own to read a mention count from directly.
      </span>
    </>
  );
}

export function RiskCountSummaryDefinition() {
  return (
    <>
      <span className="block font-bold">Risk Count Summary</span>
      <span className="block">
        How many currently-tracked risks fall into each severity band —
        Critical / High / Medium / Low, in that order — using the same
        {" "}{LOW_MAX}/{MED_MAX}/{HIGH_MAX} score cutoffs as the Risk Severity
        definition. Only documents scoring above {LOW_MAX} count as a
        tracked risk at all.
      </span>
    </>
  );
}
