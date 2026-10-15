// Shared fixtures for the report tests: the same shapes the dashboard hooks hand the report.
import { calculateSentimentDistribution } from "./calculateSentimentDistribution";
import { buildRiskHeatmap } from "./riskHeatmap";
import type { ReportInput } from "./reportModel";

export const topics = ["General", "Innovation", "Legal Risk", "Market Share", "Financial Results", "Competition"];
export function mkDocs(n: number, over: (i: number) => any = () => ({})) {
  return Array.from({ length: n }, (_, i) => {
    const flagged = i % 9 === 0;
    const unscored = i % 23 === 5;
    const risk = unscored ? null : flagged ? [29, 33, 60, 80][i % 4] : 0;
    const lvl = risk === null ? null : risk > 75 ? "CRITICAL" : risk > 50 ? "HIGH" : risk > 25 ? "MEDIUM" : "LOW";
    return {
      id: `d${i}`, title: `Doc ${i}`, source: "Feed", topic: topics[i % topics.length], sentiment: [1, 0, -1, 0.5, 0][i % 5],
      scored: risk !== null, risk: risk ?? 0, risk_exact: risk === null ? null : risk + 0.3, risk_level: lvl,
      risk_sentiment: risk === null ? null : "Negative", risk_explainability: i % 7 === 0 ? {} : { confidence: [0.2, 0.5, 0.9][i % 3] },
      original_content: "SECRET-ARTICLE-BODY", timestamp: new Date(Date.UTC(2026, 8, 1 + (i % 25), 10)).toISOString(), date_basis: i % 4 === 0 ? "collected" : "published",
      ...over(i),
    };
  });
}
export function analyticsFor(documents: any[], alerts: any[], repHistory: any[]) {
  const d = calculateSentimentDistribution(documents);
  const counts: Record<string, number> = {};
  documents.forEach(x => { const t = x.topic || "General"; counts[t] = (counts[t] || 0) + 1; });
  const buckets: Record<string, number> = {};
  alerts.forEach(a => { const k = new Date(a.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }); buckets[k] = (buckets[k] || 0) + 1; });
  return {
    sentimentDistData: [
      { name: "Positive", value: d.positive }, { name: "Neutral", value: d.neutral }, { name: "Negative", value: d.negative },
    ].filter(x => x.value > 0),
    topicDistData: Object.entries(counts).map(([name, value]) => ({ name, value })).filter(x => x.value >= 5).sort((a, b) => b.value - a.value),
    riskMatrixData: documents.map(x => ({ ...x, name: x.title, impact: x.risk, z: x.risk * 2 })),
    riskHeatmapData: buildRiskHeatmap(documents, 5),
    alertTimelineData: Object.entries(buckets).map(([date, count]) => ({ date, count })),
  };
}
export const summary = (over: any = {}) => ({
  reputation: { score: 75.51474, grade: "B", status: "ok", computed_at: "2026-10-02T15:02:27Z" },
  document_risk: { visible_documents: 140, scored_documents: 135, unscored_documents: 5, total: 14, critical: 2, high: 3, medium: 9, average: 40, highest: 80.3, as_of: "2026-10-03T05:55:00Z", top: [{ title: "Doc 0 😱 shock", risk: 29 }, { title: "Doc 9", risk: 33 }] },
  sentiment: { positive: 98, neutral: 418, negative: 49, dominant: "neutral" },
  executive_alert: { open: false, alert: null },
  ...over,
});
export const alerts = [
  { id: "a1", alert_type: "Multi-Signal Incident", severity: "HIGH", title: "Multi-Signal Incident: Acme", entity_type: "brand", created_at: "2026-10-08T11:14:24Z", ai_summary: { what: "2 risk signals.", when: "Oct 08, 2026 11:14 UTC", how_to_solve: "Review the documents." } },
  { id: "a2", alert_type: "Executive Risk", severity: "CRITICAL", title: "Exec", entity_type: "person", created_at: "2026-10-09T01:00:00Z", ai_summary: null },
];
export const hist = [
  { rawDate: "2026-09-20T00:00:00Z", date: "Sep 20", score: 72.2 }, { rawDate: "2026-10-02T15:02:00Z", date: "Oct 2", score: 75.51 },
];
export function input(over: Partial<ReportInput> = {}): ReportInput {
  const documents = mkDocs(140);
  return {
    clientId: "c1", clientName: "Acme Corp", generatedAt: new Date("2026-10-14T08:37:00Z"), userEmail: "me@example.com", browserTimeZone: "Asia/Calcutta",
    reputationSummary: summary(), reputationSummaryError: null, planAdvisory: { lead: "x", flagged: false }, planAdvisoryError: null,
    executives: [{ name: "Jane Doe", score: 80, document_count: 5, health_status: "OK" }, { name: "John Roe", score: 50, document_count: 2 }], executivesError: null,
    benchmarks: [{ competitor_name: "Rival", rank: 1, client_rank: 2, client_share_of_voice: 98.5 }], benchmarksError: null,
    documents, documentsError: null, alerts, alertsError: null, repHistory: hist, historyError: null,
    analytics: analyticsFor(documents, alerts, hist),
    ...over,
  };
}
