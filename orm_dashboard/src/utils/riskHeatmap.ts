import { docSeverity } from "@/utils/riskCenter";

export interface RiskHeatmapCell { count: number; avgRisk: number; avgSentiment: number }

// Threat Concentration Heatmap (severity x topic) for Executive Analytics. A document is banded
// with the same rule Risk Center's tiles and matrix use (docSeverity: the server's unrounded
// `risk_level`), and a document that was never risk-scored is left out of every cell: it is not a
// Low-risk document. `minTopicDocuments` is the display-only floor shared with Coverage by Topic.
export function buildRiskHeatmap(documents: any[] | null | undefined, minTopicDocuments: number) {
  const categories = Array.from(new Set((documents || []).map(d => d?.topic || "General")));
  const severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

  const grid: Record<string, Record<string, RiskHeatmapCell>> = {};
  categories.forEach(c => {
    grid[c] = {
      LOW: { count: 0, avgRisk: 0, avgSentiment: 0 },
      MEDIUM: { count: 0, avgRisk: 0, avgSentiment: 0 },
      HIGH: { count: 0, avgRisk: 0, avgSentiment: 0 },
      CRITICAL: { count: 0, avgRisk: 0, avgSentiment: 0 }
    };
  });

  (documents || []).forEach(d => {
    if (d) {
      const sev = docSeverity(d);
      if (sev === null) return;
      const c = d.topic || "General";
      const r = d.risk || 0;
      const s = d.sentiment || 0;
      if (grid[c] && grid[c][sev]) {
        grid[c][sev].count++;
        grid[c][sev].avgRisk += r;
        grid[c][sev].avgSentiment += s;
      }
    }
  });

  categories.forEach(c => {
    severities.forEach(sev => {
      if (grid[c][sev].count > 0) {
        grid[c][sev].avgRisk = grid[c][sev].avgRisk / grid[c][sev].count;
        grid[c][sev].avgSentiment = grid[c][sev].avgSentiment / grid[c][sev].count;
      }
    });
  });

  const visibleCategories = categories.filter(c => {
    const total = severities.reduce((sum, sev) => sum + grid[c][sev].count, 0);
    return total >= minTopicDocuments;
  });

  return { categories: visibleCategories, severities, grid };
}
