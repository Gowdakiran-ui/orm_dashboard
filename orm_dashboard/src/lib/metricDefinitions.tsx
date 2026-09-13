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

/**
 * "Critical Risks" (this tile) vs. an Active Alert's own "CRITICAL" badge --
 * these can legitimately disagree (xoop_ui_clarity_review.md: "0 Critical
 * Risks" next to "1 Active -- CRITICAL" read as a contradiction). Traced
 * against alert_engine.py: an alert's severity comes from a separate
 * evidence_score (risk + trend + document-count + executive-mention
 * weighting combined, >70 or any executive involvement = CRITICAL), not
 * from any single document crossing this tile's per-document Risk Score
 * threshold. Two different signals, same word -- not a bug to reconcile.
 */
export function CriticalRisksVsActiveAlertsDefinition() {
  return (
    <>
      <span className="block font-bold">Critical Risks vs. Active Alerts</span>
      <span className="block">
        This tile counts documents whose own Risk Score crosses the Critical
        threshold ({HIGH_MAX}+). An Active Alert&apos;s CRITICAL badge is a
        separate signal -- it can fire from a combination of risk, trend
        velocity, document volume, and executive involvement even when no
        single document is itself Critical-risk.
      </span>
    </>
  );
}

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

export function DocumentsAnalyzedDefinition() {
  return (
    <>
      <span className="block font-bold">Documents Analyzed</span>
      <span className="block">
        Every document collected and processed for this client, whether or
        not it turned out to carry any risk — this is a coverage-volume
        count, not a count of confirmed risk incidents. For the count of
        actual tracked risks, see Risk Center&apos;s &quot;Total Risks&quot;.
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
      <span className="block mt-1">
        <b>Innovation</b> (product/competitive-positioning coverage, e.g.
        pricing changes) carries no inherent topic weight of its own
        (risk_config.py&apos;s TOPIC_WEIGHTS has no entry for it) -- its Risk
        Score comes entirely from that document&apos;s sentiment, trend, and
        source-reliability signals. That&apos;s why an Innovation-tagged
        article can still register a non-trivial risk score even when the
        underlying news is neutral or positive for the company.
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

/**
 * ExecutivesTab.tsx's "Sentiment Breakdown" chart -- buckets each piece of
 * coverage mentioning the selected executive by its per-document sentiment
 * score (ExecutivesTab.tsx sentimentData: >0.25 positive, <-0.25 negative,
 * otherwise neutral). These +/-0.25 cut points are this chart's own bucketing
 * choice, distinct from the underlying -1..+1 sentiment scale itself (see
 * SentimentScaleDefinition).
 */
export function ExecutiveSentimentBreakdownDefinition() {
  return (
    <>
      <span className="block font-bold">Sentiment Breakdown</span>
      <span className="block">
        Buckets this executive&apos;s coverage by each document&apos;s
        sentiment score (-1.0 to +1.0):
      </span>
      <span className="mt-1 block"><b>Positive</b> — above +0.25</span>
      <span className="block"><b>Negative</b> — below -0.25</span>
      <span className="block"><b>Neutral</b> — everything in between</span>
    </>
  );
}

/**
 * ExecutivesTab.tsx's Executive Scorecard table -- Confidence, Evidence
 * Coverage and Trend columns. Traced directly against
 * executive_reputation_engine.py's calculate_executive_reputation:
 *   - doc_confidence = min(document_count / 10, 1.0)
 *   - signal_completeness = 0.5x(1.0 if recent risk data else 0.5) +
 *       0.5x(1.0 if recent trend data else 0.5)
 *   - confidence_score = doc_confidence*0.6 + signal_completeness*0.4
 *     (0.0 whenever there's no qualifying evidence at all)
 *   - data_coverage is written from that same confidence_score value --
 *     the engine reuses it rather than computing a second, separate number.
 *   - Trend compares this run's score to the previous one: +2.0 or more is
 *     IMPROVING, -2.0 or more is DECLINING, otherwise STABLE (and there's no
 *     prior score to compare, it reports STABLE).
 */
export function ExecutiveScorecardMetricsDefinition() {
  return (
    <>
      <span className="block font-bold">Confidence, Evidence Coverage &amp; Trend</span>
      <span className="block">
        <b>Confidence</b> blends how much recent coverage exists (capped once
        10+ documents are seen in the last 30 days) with whether recent risk
        and trend signal was available for this executive.
      </span>
      <span className="mt-1 block">
        <b>Evidence Coverage</b> reuses that same Confidence value — it is not
        a separate calculation.
      </span>
      <span className="mt-1 block">
        <b>Trend</b> compares this run&apos;s Reputation Score to the previous
        one: IMPROVING (+2.0 or more), DECLINING (-2.0 or more), otherwise
        STABLE.
      </span>
    </>
  );
}

/**
 * OverviewAnalyticsPanel.tsx's "Coverage by Topic" bar chart -- a plain
 * count of every monitored document grouped by its classified topic
 * (useAnalytics.ts topicDistData: d.topic, falling back to "General"),
 * ranked highest to lowest.
 */
export function CoverageByTopicDefinition() {
  return (
    <>
      <span className="block font-bold">Coverage by Topic</span>
      <span className="block">
        How many monitored documents fall under each classified topic, across
        this client&apos;s entire feed — ranked from most to least covered.
      </span>
    </>
  );
}

/**
 * OverviewAnalyticsPanel.tsx's "Sentiment Breakdown" pie chart -- backed by
 * utils/calculateSentimentDistribution.ts, which buckets every document with
 * a sentiment score by a +/-0.3 cut point. This is a different, wider cutoff
 * than ExecutivesTab.tsx's own +/-0.25 bucketing of a single executive's
 * coverage (see ExecutiveSentimentBreakdownDefinition) -- each chart uses
 * its own threshold, so they are named and explained separately rather than
 * sharing one definition that would misdescribe one of them.
 */
export function OverviewSentimentBreakdownDefinition() {
  return (
    <>
      <span className="block font-bold">Sentiment Breakdown</span>
      <span className="block">
        Buckets every document in this client&apos;s feed by its sentiment
        score (-1.0 to +1.0):
      </span>
      <span className="mt-1 block"><b>Positive</b> — above +0.3</span>
      <span className="block"><b>Negative</b> — below -0.3</span>
      <span className="block"><b>Neutral</b> — everything in between</span>
    </>
  );
}

/**
 * OverviewAnalyticsPanel.tsx's "Average Sentiment Over Time" line chart --
 * useAnalytics.ts sentimentTrendData averages each document's sentiment
 * score (-1.0/0.0/+1.0 per SentimentScaleDefinition) within each calendar
 * day. Hovering a point that moved by 0.25 or more from the prior day also
 * surfaces the narrative most likely driving that shift, when one is linked.
 */
export function AverageSentimentTrendDefinition() {
  return (
    <>
      <span className="block font-bold">Average Sentiment Over Time</span>
      <span className="block">
        Each point is the average sentiment score (-1.0 to +1.0) across every
        document published that day. A day-over-day move of 0.25 or more is
        treated as meaningful and, when a narrative is linked to it, shows
        that narrative&apos;s driving root cause on hover.
      </span>
    </>
  );
}

/**
 * RiskAnalyticsPanel.tsx's "Daily Alerts Trigger Volume Timeline" -- a count
 * of alert records (alert_engine.py's risk/trend/executive alert
 * evaluators) triggered each day for this client, across every severity.
 */
export function DailyAlertsTimelineDefinition() {
  return (
    <>
      <span className="block font-bold">Daily Alerts Trigger Volume</span>
      <span className="block">
        How many alerts — risk, trend, or executive-reputation alerts —
        fired for this client on each day, across every severity level.
      </span>
    </>
  );
}

/**
 * RiskAnalyticsPanel.tsx's "Threat Concentration Heatmap (Severity × Topic)"
 * -- each cell is the document count for one (topic, severity) pair over
 * the current feed, using the same LOW/MEDIUM/HIGH/CRITICAL bands as Risk
 * Severity (see RiskSeverityDefinition), plus that cell's average Risk
 * Score and average sentiment shown on hover.
 */
export function ThreatConcentrationHeatmapDefinition() {
  return (
    <>
      <span className="block font-bold">Threat Concentration Heatmap</span>
      <span className="block">
        Each cell counts documents that share both a topic and a Risk
        Severity band (Low/Medium/High/Critical — same cutoffs as Risk
        Severity). Row and column totals show how concentrated risk is by
        topic vs. by severity; hovering a cell also shows its average Risk
        Score and average sentiment.
      </span>
      <span className="block mt-1">
        <b>R:</b> that cell&apos;s average Risk Score (0–100). <b>S:</b> its
        average sentiment (-1.0 to +1.0).
      </span>
    </>
  );
}

/**
 * NarrativeAnalyticsPanel.tsx's "Narrative Landscape Matrix (Velocity ×
 * Risk)" bubble chart. Traced against narrative_engine.py:
 *   - Velocity (X axis, "strength" in narrativeBubbleData) is the absolute
 *     value of the narrative's trend_strength -- a % change in that
 *     narrative's coverage volume (TrendEvent.percentage_change), not a
 *     directional value.
 *   - Risk (Y axis) is the narrative's average Risk Score (0-100), the same
 *     scale as Risk Severity elsewhere in this dashboard.
 *   - Bubble size is mention volume (document count in the narrative
 *     cluster), log-scaled on the frontend only so a handful of very large
 *     narratives don't dwarf every other bubble.
 */
export function NarrativeVelocityRiskDefinition() {
  return (
    <>
      <span className="block font-bold">Narrative Landscape: Velocity × Risk</span>
      <span className="block">
        <b>Velocity</b> (x-axis) — the size of the recent % change in that
        narrative&apos;s coverage volume, regardless of direction.
      </span>
      <span className="mt-1 block">
        <b>Risk</b> (y-axis) — the narrative&apos;s average Risk Score (0–100),
        the same scale used everywhere else in this dashboard.
      </span>
      <span className="mt-1 block">
        <b>Bubble size</b> — how many documents are in that narrative&apos;s
        cluster, log-scaled here only so very large narratives don&apos;t
        dwarf the rest of the chart.
      </span>
    </>
  );
}

/**
 * NarrativeAnalyticsPanel.tsx's "Daily Ingestion Ingestion Volume" stacked
 * area chart -- a per-day count of every monitored document, stacked by
 * its source.
 */
export function DailyIngestionVolumeDefinition() {
  return (
    <>
      <span className="block font-bold">Daily Ingestion Volume</span>
      <span className="block">
        How many documents this client&apos;s feed ingested each day, stacked
        by which source (RSS, Reddit, Instagram, etc.) they came from.
      </span>
    </>
  );
}

/**
 * NarrativeAnalyticsPanel.tsx's "Sources Distribution Matrix" ranked bar
 * chart -- a plain count of every monitored document grouped by source,
 * across the whole feed (not just one day).
 */
export function SourcesDistributionDefinition() {
  return (
    <>
      <span className="block font-bold">Sources Distribution</span>
      <span className="block">
        Total document count per source (RSS, Reddit, Instagram, etc.) across
        this client&apos;s entire feed, ranked highest to lowest.
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
