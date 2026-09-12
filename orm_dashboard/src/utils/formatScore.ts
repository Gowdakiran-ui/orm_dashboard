import type { ReactNode } from "react";

// Single shared formatter for any numeric score/metric rendered in a chart
// tooltip or label. Recharts' default Tooltip renders whatever raw number is
// in the data (e.g. reputation_score = 67.6922300247609) with zero rounding.
// This was previously patched ad-hoc per chart (one inline .toFixed(2) in
// OverviewAnalyticsPanel's sentiment trend Tooltip) instead of fixed once --
// exactly the "same thing computed slightly differently in different places"
// pattern that has caused repeat bugs in this project (Likelihood formula,
// AI-summary visibility scoping). Use this everywhere a score renders instead
// of a local toFixed call.
export function formatScore(value: unknown, decimals: number = 2): ReactNode {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return value as ReactNode;
  }
  return value.toFixed(decimals);
}

// Recharts' <Tooltip formatter> is called as (value, name, item, index,
// payload) -- passing formatScore directly makes TS read its own optional
// `decimals` param as that `name` slot and reject the assignment. Use this
// wrapper as the `formatter` prop instead; it discards the extra Recharts
// arguments and always applies the default 2-decimal rounding.
export function tooltipScoreFormatter(value: unknown): ReactNode {
  return formatScore(value);
}
