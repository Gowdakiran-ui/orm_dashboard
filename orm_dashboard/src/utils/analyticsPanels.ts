// Pure logic behind the Executive Analytics panels (OverviewAnalyticsPanel, RiskAnalyticsPanel). Kept free of
// React so the panels and the exported report read the same functions and can never disagree.
import { formatReputationScore, type ReputationBlock, sourceState } from "@/utils/brandEquity";

// ---- Reputation & Sentiment History ----------------------------------------------------------------
// Same "too few to trust" floor risk_engine.py already uses for trend significance (risk_engine.py:790,796).
export const SENTIMENT_SCORE_MIN_SAMPLE = 5;

export interface OverviewKpiValues {
  currentReputation: string;
  topicsCovered: number;
  positiveCount: number;
  negativeCount: number;
  sentimentTotal: number;
  hasEnoughSentimentData: boolean;
  // (positive - negative) / total, or null when there are too few readings.
  sentimentScore: number | null;
  // Percent of readings that are positive, or null when there are none.
  positiveShare: number | null;
}

export function overviewKpiValues(i: {
  reputation: ReputationBlock | null | undefined;
  topicDistData: any[];
  sentimentDistData: any[];
}): OverviewKpiValues {
  const posVal = i.sentimentDistData.find(d => d.name === "Positive")?.value || 0;
  const negVal = i.sentimentDistData.find(d => d.name === "Negative")?.value || 0;
  const totalVal = i.sentimentDistData.reduce((acc, curr) => acc + (curr.value || 0), 0);
  const hasEnoughSentimentData = totalVal >= SENTIMENT_SCORE_MIN_SAMPLE;
  return {
    currentReputation: formatReputationScore(i.reputation),
    topicsCovered: i.topicDistData.length,
    positiveCount: posVal,
    negativeCount: negVal,
    sentimentTotal: totalVal,
    hasEnoughSentimentData,
    sentimentScore: hasEnoughSentimentData ? (posVal - negVal) / totalVal : null,
    positiveShare: totalVal > 0 ? (posVal / totalVal) * 100 : null,
  };
}

// The Sentiment Score tile's text.
export function formatSentimentScoreKpi(v: number | null): string {
  return v === null ? "Not enough data yet" : v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2);
}

// The Positive Share tile's text (the screen shows 0% when there are no readings).
export function formatPositiveShareKpi(v: number | null): string {
  return v === null ? "0%" : `${v.toFixed(0)}%`;
}

// The trend component was removed from the score on 2026-10-01, so scores stored before that date were
// computed with a slightly different method (up to about 3 points). The history itself is left exactly as
// stored; this only marks where the method changed.
export const SCORING_CHANGE_ISO = "2026-10-01T00:00:00Z";
export const SCORING_CHANGE_NOTE =
  "Scoring method updated 1 Oct 2026: earlier scores include a component that has since been removed and can differ by up to about 3 points.";

export function scoringMethodChange(repHistory: any[] | null | undefined) {
  const cutoff = new Date(SCORING_CHANGE_ISO).getTime();
  const dated = (repHistory || []).filter((h: any) => h && h.rawDate && !Number.isNaN(new Date(h.rawDate).getTime()));
  const hasEarlier = dated.some((h: any) => new Date(h.rawDate).getTime() < cutoff);
  const firstAfter = dated.find((h: any) => new Date(h.rawDate).getTime() >= cutoff);
  return { hasEarlier, markerDate: hasEarlier && firstAfter ? (firstAfter.date as string) : null };
}

// ---- Risk & Alert Profile --------------------------------------------------------------------------
export function riskPanelFacts(i: {
  riskMatrixData: any[];
  reputationSummary?: any;
  reputationSummaryLoading?: boolean;
  reputationSummaryError?: string | null;
  alertTimelineData: any[];
}) {
  // True totals come from the server (same source as Risk Center's tiles); the charts and the matrix are
  // built from the newest articles the page loads (at most 500), and the page says so whenever that is
  // fewer than the total.
  const summaryReady = sourceState(i.reputationSummaryLoading, i.reputationSummaryError) === "ready";
  const docRisk = summaryReady ? i.reputationSummary?.document_risk : null;
  const visibleTotal: number | null = typeof docRisk?.visible_documents === "number" ? docRisk.visible_documents : null;
  const flaggedTotal: number | null = typeof docRisk?.total === "number" ? docRisk.total : null;
  const criticalTotal: number | null = typeof docRisk?.critical === "number" ? docRisk.critical : null;
  const loadedCount = i.riskMatrixData.length;
  const loadedNote = visibleTotal !== null && loadedCount < visibleTotal
    ? `Showing the newest ${loadedCount} of ${visibleTotal} articles in the charts and matrix below.`
    : null;
  const openAlerts = i.alertTimelineData.reduce((sum: number, d: any) => sum + (d?.count || 0), 0);
  // Only articles that have actually been risk-scored: an unscored article is not a zero-risk article.
  const scoredList = i.riskMatrixData.filter(d => d.scored === true && typeof d.risk === "number");
  const avgRiskVal = scoredList.length > 0 ? scoredList.reduce((sum, d) => sum + d.risk, 0) / scoredList.length : null;
  const alertsStatus = openAlerts === 0 ? "No open alerts" : `${openAlerts} open ${openAlerts === 1 ? "alert" : "alerts"}`;
  return { visibleTotal, flaggedTotal, criticalTotal, loadedCount, loadedNote, openAlerts, scoredCount: scoredList.length, avgRiskVal, alertsStatus };
}

export function alertTimelineStats(alertTimelineData: any[] | null | undefined) {
  if (!alertTimelineData || alertTimelineData.length === 0) return { avg: 0, peakDate: "", peakCount: 0 };
  const counts = alertTimelineData.map(d => d.count || 0);
  const sum = counts.reduce((a, b) => a + b, 0);
  const avg = Number((sum / alertTimelineData.length).toFixed(1));
  let maxIdx = 0;
  for (let i = 1; i < counts.length; i++) {
    if (counts[i] > counts[maxIdx]) maxIdx = i;
  }
  return { avg, peakDate: alertTimelineData[maxIdx]?.date || "", peakCount: alertTimelineData[maxIdx]?.count || 0 };
}

// Row, column and grand totals of the Threat Concentration Heatmap.
export function heatmapTotals(riskHeatmapData: any) {
  const rowTotals: Record<string, number> = {};
  const colTotals: Record<string, number> = {};
  let grandTotal = 0;
  if (riskHeatmapData && riskHeatmapData.categories) {
    riskHeatmapData.categories.forEach((cat: string) => {
      rowTotals[cat] = 0;
      riskHeatmapData.severities.forEach((sev: string) => {
        const count = riskHeatmapData.grid[cat]?.[sev]?.count || 0;
        rowTotals[cat] += count;
        colTotals[sev] = (colTotals[sev] || 0) + count;
        grandTotal += count;
      });
    });
  }
  return { rowTotals, colTotals, grandTotal };
}
