// Intelligence Stream order: flagged articles first (strongest risk first, then newest), then the newest articles.
//
// The stream loads the newest 500 articles. For a client with a long history those can all be LOW, which pushed every flagged article out
// of the list (Godrej: 18 flagged of 1,771, none among the newest 500). The server now also returns the flagged articles of any age; this
// puts them on top, without repeating one that is also in the newest list. Display only: nothing here changes a score or a count.

const num = (v: any): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const time = (d: any): number => {
  const t = typeof d?.timestamp === "string" ? new Date(d.timestamp).getTime() : NaN;
  return Number.isNaN(t) ? 0 : t;
};

// Strongest risk first (the unrounded score when present), then newest, then id so the order never wobbles between refreshes.
export function byRiskThenDate(a: any, b: any): number {
  return (num(b?.risk_exact ?? b?.risk) - num(a?.risk_exact ?? a?.risk)) || (time(b) - time(a)) || String(a?.id).localeCompare(String(b?.id));
}

export function orderStream(recent: any[] | null | undefined, flagged: any[] | null | undefined): any[] {
  const list = Array.isArray(recent) ? recent : [];
  const top = (Array.isArray(flagged) ? flagged : []).filter(d => d && d.id);
  if (top.length === 0) return list;
  const ids = new Set(top.map(d => d.id));
  return [...[...top].sort(byRiskThenDate), ...list.filter(d => !(d && ids.has(d.id)))];
}

// How many articles lead the list because they are flagged (0 when no flagged list came back).
export function flaggedLeadCount(ordered: any[], flagged: any[] | null | undefined): number {
  if (!Array.isArray(flagged) || flagged.length === 0) return 0;
  const ids = new Set(flagged.filter(d => d && d.id).map(d => d.id));
  return ordered.filter(d => d && ids.has(d.id)).length;
}
