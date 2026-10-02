// A 0-1 fraction (confidence_score, data_coverage) as a whole-number percent.
// Missing / null / non-numeric means "unknown", never 0% or NaN%.
export function formatFractionAsPercent(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(0)}%` : "Unknown";
}
