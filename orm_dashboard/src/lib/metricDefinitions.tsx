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
 * evidence_score (risk + document-count + executive-mention
 * weighting combined, >70 or any executive involvement = CRITICAL), not
 * from any single document crossing this tile's per-document Risk Score
 * threshold. Two different signals, same word -- not a bug to reconcile.
 */
export function CriticalRisksVsActiveAlertsDefinition() {
  return (
    <>
      <span className="block font-bold">Critical articles vs. Active Alerts</span>
      <span className="block">
        The Critical count is the number of flagged articles whose own risk
        score is above {HIGH_MAX}. An Active Alert&apos;s CRITICAL badge is a
        separate signal -- it can fire from a combination of risk,
        article volume, and executive involvement even when no
        single article is itself Critical.
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
        A 0–100 score blending sentiment (30%), risk (30%), source
        reliability (10%) and media visibility (5%) over a rolling window,
        weighted by how much signal is actually available for each part.
      </span>
    </>
  );
}

/**
 * Risk Center's "Flagged articles" tile (RiskTab.tsx). The unit is ARTICLES:
 * one story reported by several outlets counts once per outlet. Counted over
 * every article collected for the client (server-side, utils/riskCenter.ts
 * tilesFromSummary), not only the newest 500 the table lists.
 */
export function FlaggedArticlesDefinition() {
  return (
    <>
      <span className="block font-bold">Flagged articles</span>
      <span className="block">
        {"The number of collected articles whose risk score is above "}{LOW_MAX}{" (Medium severity or higher). Each article counts once, even when several outlets report the same story, and articles of any age are included."}
      </span>
    </>
  );
}

/**
 * The Severity x Confidence matrix, shown on Risk Center (RiskTab.tsx) and on
 * Executive Analytics (RiskAnalyticsPanel.tsx): rows are the platform severity
 * bands, so a flagged article is in the same band here as in the table and
 * the tiles. Columns are the engine's confidence value
 * (risk_engine.py explainability.confidence = (topic_conf + sentiment_conf)
 * / 2), shown in thirds. Both pages build it with utils/riskCenter.ts
 * buildMatrix, so a cell holds the same articles on both.
 */
export function RiskMatrixSeverityConfidenceDefinition() {
  return (
    <>
      <span className="block font-bold">Risk Matrix: Severity × Confidence</span>
      <span className="block">
        {"Rows are the severity band of each flagged article: Medium ("}{LOW_MAX}{"–"}{MED_MAX}{"), High ("}{MED_MAX}{"–"}{HIGH_MAX}{") or Critical (above "}{HIGH_MAX}{"). The same bands are used in the table and the tiles."}
      </span>
      <span className="mt-1 block">
        {"Confidence is how sure the system is about the signals it scored the article on (its tone and subject), from 0 to 100, shown as Low (under 33), Medium (33–66) or High (67+). It is not a prediction that the risk will happen or recur."}
      </span>
    </>
  );
}

export function DocumentsAnalyzedDefinition() {
  return (
    <>
      <span className="block font-bold">Documents Analyzed</span>
      <span className="block">
        All articles collected for this client, whether or not they carry
        any risk, including those not yet risk-checked. This is a volume
        count over every article, not only the newest ones listed in the
        charts, and not a count of confirmed risk incidents. For the count
        of flagged articles, see Risk Center&apos;s &quot;Flagged articles&quot;.
      </span>
    </>
  );
}

export function AverageRiskScoreFeedDefinition() {
  return (
    <>
      <span className="block font-bold">Average Risk Score</span>
      <span className="block">
        The mean Risk Score (0–100) across the articles listed on this page
        (the newest ones, up to 500), including articles that scored 0 risk.
        It is not tied to any single story; Risk Center shows the average
        of flagged articles only.
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
 * Competitor Compare radar chart (CompetitorsTab.tsx, built by utils/competitorCompare.ts buildRadarData)
 * and its Comparable Score / Share of Voice bar charts below it. Every axis is on ONE basis for the client
 * and the competitor (audit/competitors-audit.md F-01, F-04):
 *   - Comparable Score: BenchmarkEngine's score (weighted sentiment / risk / source / visibility, last 30 days,
 *     only articles that also mention the client). The client gets the same calculation
 *     (`client_comparable_score` on /benchmark), not its overall reputation score.
 *   - Sentiment Score: average tone from -1..+1 shown as 0-100 (50 = neutral).
 *   - Risk Containment: 100 minus the average risk score. The client's stored risk component already is
 *     "100 minus average risk", so it is shown as it is.
 *   - Share of Voice: a competitor's mentions / (client + compared competitors' mentions) x 100, counting
 *     only articles that also mention the client; the client is the remainder (utils/shareOfVoice.ts).
 */
export function CompetitorRadarAxesDefinition() {
  return (
    <>
      <span className="block font-bold">Competitor Comparison Metrics</span>
      <span className="block">
        <b>Comparable Score</b> (0–100) — one score calculated the same way for
        the client and the competitor over the last 30 days, using only
        articles that also mention the client. It is not the overall
        reputation score shown on Brand Equity.
      </span>
      <span className="mt-1 block">
        <b>Sentiment Score</b> — average coverage tone, normalized from the
        -1.0..+1.0 scale to 0–100 for this chart (50 = neutral).
      </span>
      <span className="mt-1 block">
        <b>Risk Containment</b> — 100 minus the average Risk Score, so a
        higher value always means lower risk exposure. Only articles that
        also mention the client are included, so a competitor&apos;s other
        stories do not count here.
      </span>
      <span className="mt-1 block">
        <b>Share of Voice</b> — the share of all mentions (the client plus the
        compared competitors) that belong to this entity, counting only
        articles that also mention the client.
      </span>
    </>
  );
}

/** Competitors tab "Comparable Score Compare" card (page-only; Brand Equity keeps ReputationScoreDefinition). */
export function CompetitorComparableScoreDefinition() {
  return (
    <>
      <span className="block font-bold">Comparable Score</span>
      <span className="block">
        A 0–100 score that blends sentiment (30%), risk (30%), source
        reliability (10%) and media visibility (5%), re-weighted over the parts
        that have data. It is calculated the same way for the client and for
        the competitor, over the last 30 days, using only articles that also
        mention the client, so the two bars can be compared. It is not the
        overall reputation score shown on Brand Equity.
      </span>
    </>
  );
}

/** Competitors tab Share of Voice text (page-only; Brand Equity keeps ShareOfVoiceDefinition). */
export function CompetitorShareOfVoiceDefinition() {
  return (
    <>
      <span className="block font-bold">Share of Voice (SOV)</span>
      <span className="block">
        A competitor&apos;s share of all mentions in the last 30 days: its
        mention count divided by (the client&apos;s + every compared
        competitor&apos;s mention count). Only articles that also mention the
        client are counted, so coverage of a competitor elsewhere does not
        show up here. The client&apos;s own share is 100 minus the sum of the
        compared competitors&apos; shares, never below 0.
      </span>
    </>
  );
}

/**
 * Competitor Compare's Topic Ownership chart (CompetitorsTab.tsx) --
 * benchmark_engine.py's get_topic_distribution: for the client and every
 * tracked competitor, counts each qualifying document (same 30-day window
 * and brand-co-occurrence gate as the rest of this page) by its single
 * highest-confidence classified topic (documents.py's own convention for
 * a multi-labeled document; falls back to "General" when a document has no
 * topic row at all).
 */
export function TopicOwnershipDefinition() {
  return (
    <>
      <span className="block font-bold">Topic Ownership</span>
      <span className="block">
        Each entity&apos;s coverage over the last 30 days, grouped by its
        highest-confidence classified topic — the same per-document topic
        shown elsewhere on this dashboard.
      </span>
      <span className="mt-1 block">
        <b>Known limitation:</b> the 17-topic taxonomy is shared across every
        client on this platform regardless of industry, so a category can
        read as structurally irrelevant for some clients (e.g. an AI company
        showing an automotive-flavored category). Treat this as directional,
        not precise.
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
 * ExecutivesTab.tsx's tracked-executive search result card -- the Grade
 * shown there comes from ExecutiveReputationEngine, a SEPARATE engine from
 * the client-level ReputationEngine (see ReputationGradeDefinition/
 * ReputationScoreDefinition above): same letter-grade cutoffs, but its own
 * weights (executive_reputation_engine.py __init__: sentiment 35%, risk 30%,
 * visibility 10%, each dropped and the rest re-normalized if that
 * signal has no data for this person). A low grade with very little tracked
 * coverage most often means too few mentions to carry much weight, not
 * necessarily sustained negative coverage.
 */
export function ExecutiveReputationGradeDefinition() {
  return (
    <>
      <span className="block font-bold">Executive Reputation Grade</span>
      <span className="block">
        This person&apos;s Score (0–100) blends sentiment (35%), risk (30%)
        and mention visibility (10%) from their own tracked coverage, then
        maps to a letter grade:
      </span>
      <span className="mt-1 block"><b>A+</b> 90–100 &nbsp; <b>A</b> 80–89.9</span>
      <span className="block"><b>B</b> 70–79.9 &nbsp; <b>C</b> 60–69.9</span>
      <span className="block"><b>D</b> 40–59.9 &nbsp; <b>F</b> below 40</span>
      <span className="mt-1 block">
        Grades are per-person, not per-client — a low grade with only a
        handful of tracked mentions reflects thin coverage as much as
        negative sentiment.
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
 * ExecutivesTab.tsx's Executive Scorecard table -- Confidence and Evidence
 * Coverage columns. Traced directly against
 * executive_reputation_engine.py's calculate_executive_reputation:
 *   - doc_confidence = min(document_count / 10, 1.0)
 *   - signal_completeness = 1.0 if recent risk data else 0.5
 *   - confidence_score = doc_confidence*0.6 + signal_completeness*0.4
 *     (0.0 whenever there's no qualifying evidence at all)
 *   - data_coverage is written from that same confidence_score value --
 *     the engine reuses it rather than computing a second, separate number.
 */
export function ExecutiveScorecardMetricsDefinition() {
  return (
    <>
      <span className="block font-bold">Confidence &amp; Evidence Coverage</span>
      <span className="block">
        <b>Confidence</b> blends how much recent coverage exists (capped once
        10+ documents are seen in the last 30 days) with whether recent risk
        signal was available for this executive.
      </span>
      <span className="mt-1 block">
        <b>Evidence Coverage</b> reuses that same Confidence value — it is not
        a separate calculation.
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
 * ReputationSummaryCard.tsx's "Positive Signals" / "Dominant Sentiment"
 * tiles and Overview paragraph -- a THIRD, differently-scoped sentiment split from the two
 * document-threshold-based ones above. This one comes straight from the
 * backend (client_intelligence.py get_reputation_summary): a count of
 * EntitySentiment rows (one per entity x document pair) whose
 * categorical sentiment_label was set by sentiment_analyzer.py, scoped to
 * this client's own brand/product/person entities only (competitor entities
 * excluded) and to documents that also mention the client's brand/product.
 * Because it counts entity-document readings with a pre-assigned label,
 * not documents bucketed by a numeric cutoff, its totals will not match
 * either Sentiment Breakdown chart's positive/neutral/negative counts.
 */
export function EntitySentimentSplitDefinition() {
  return (
    <>
      <span className="block font-bold">Mentions &amp; overall tone</span>
      <span className="block">
        A mention is one appearance of the client&apos;s brand, one of its
        products, or a tracked person in one piece of coverage, labelled
        Positive, Neutral or Negative by the sentiment model. Only coverage
        that also mentions the client&apos;s own brand or product counts, and
        tracked competitors are left out.
      </span>
      <span className="mt-1 block">
        One article can hold several mentions (one for the brand, one for each
        person), so this is not an article count and will not match the
        Sentiment Breakdown charts on Executive Analytics. If the two most
        common tones tie, the overall tone is shown as &quot;mixed&quot;.
      </span>
    </>
  );
}

/**
 * OverviewAnalyticsPanel.tsx's "Average Sentiment History" line chart --
 * useAnalytics.ts sentimentHistoryData averages each document's sentiment
 * score (-1.0/0.0/+1.0 per SentimentScaleDefinition) within each calendar
 * day. Raw daily values only; nothing is interpreted.
 */
export function AverageSentimentHistoryDefinition() {
  return (
    <>
      <span className="block font-bold">Average Sentiment History</span>
      <span className="block">
        Each point is the average sentiment score (-1.0 to +1.0) across every
        document published that day.
      </span>
    </>
  );
}

/**
 * RiskAnalyticsPanel.tsx's "Daily Alerts Trigger Volume Timeline" -- a count
 * of alert records (alert_engine.py's risk/executive alert
 * evaluators) triggered each day for this client, across every severity.
 */
export function DailyAlertsTimelineDefinition() {
  return (
    <>
      <span className="block font-bold">Daily Alerts Trigger Volume</span>
      <span className="block">
        How many alerts — risk or executive-reputation alerts —
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

export function RiskCountSummaryDefinition() {
  return (
    <>
      <span className="block font-bold">Risk Count Summary</span>
      <span className="block">
        How many tracked risks, counted over all collected documents (all time, not a recent window), fall into each severity band —
        Critical / High / Medium / Low, in that order — using the same
        {" "}{LOW_MAX}/{MED_MAX}/{HIGH_MAX} score cutoffs as the Risk Severity
        definition. Only documents scoring above {LOW_MAX} count as a
        tracked risk at all.
      </span>
    </>
  );
}

/**
 * "Competitor Rank / Share of Voice" (dashboard home) vs. Competitor
 * Compare's "No tracked competitors yet" -- traced against
 * benchmark_engine.py: this tile is computed automatically from every
 * entity_type='competitor' entity discovered in this client's own passive
 * coverage (with real document evidence, i.e. a computed reputation
 * score), not from Competitor Compare's separate opt-in "search a name to
 * start tracking" feature. A client can have this tile populated while
 * genuinely tracking zero competitors on that page -- not a contradiction
 * once the two are understood as different signals over different data.
 */
export function CompetitorRankShareOfVoiceDefinition() {
  return (
    <>
      <span className="block font-bold">Competitor Rank / Share of Voice</span>
      <span className="block">
        Computed automatically from every competitor entity found in this
        client&apos;s own coverage with enough evidence to score -- a
        passive, always-on signal. This is a different list than Competitor
        Compare&apos;s page, which only shows competitors you&apos;ve
        explicitly searched and started tracking there. It&apos;s expected
        for this tile to show a rank/SOV while that page still reads &quot;No
        tracked competitors yet.&quot;
      </span>
    </>
  );
}
