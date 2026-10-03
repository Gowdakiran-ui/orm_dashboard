// Pure helpers for the Competitors tab (audit/competitors-audit.md F-01, F-02, F-04, F-05, F-06, F-09, F-10, F-12).
// Everything here is plain data in / plain data out so each rule can be tested without rendering the page.

export const ACTIVITY_ARTICLE_CAP = 500; // the page's /documents/client list is the newest 500 articles
export const MIN_TOPIC_COMPARISON_COUNT = 5;
// Display-only: a score that rests on fewer mentions than this gets a "Low evidence" badge. No score or rank changes.
export const LOW_EVIDENCE_MENTIONS = 3;

export type RadarValues = { reputation: number | null; sentiment: number | null; riskContainment: number | null; sov: number | null };

export const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

/** A competitor row from competitor-search has no usable numbers when the engine had no evidence. */
export function hasEvidence(c: any): boolean {
  return !!c && c.health_status !== "INSUFFICIENT_EVIDENCE" && isNum(c.reputation_score);
}

/**
 * The client's point on the radar, on the SAME basis as the competitors:
 *  - reputation: the engine's comparable score for the client (`client_comparable_score` on /benchmark), not the overall score;
 *  - sentiment: the client's sentiment component (already 0-100);
 *  - risk containment: the client's risk component, which the reputation engine already stores as
 *    `100 - average risk` (higher = safer). It must NOT be subtracted from 100 again;
 *  - share of voice: the remainder after every compared competitor.
 * Anything that is not a number stays null; it is never turned into 0.
 */
export function clientRadarValues(comparableScore: unknown, breakdown: any, clientSov: number | null): RadarValues {
  return {
    reputation: isNum(comparableScore) ? comparableScore : null,
    sentiment: isNum(breakdown?.sentiment) ? breakdown.sentiment : null,
    riskContainment: isNum(breakdown?.risk) ? breakdown.risk : null,
    sov: isNum(clientSov) ? clientSov : null,
  };
}

/** The competitor's point on the radar; null when the engine had no evidence for it. */
export function competitorRadarValues(c: any): RadarValues | null {
  if (!hasEvidence(c)) return null;
  return {
    reputation: c.reputation_score,
    sentiment: isNum(c.sentiment_score) ? (c.sentiment_score + 1) * 50 : null,
    riskContainment: isNum(c.risk_score) ? 100 - c.risk_score : null,
    sov: isNum(c.share_of_voice) ? c.share_of_voice : null,
  };
}

export const RADAR_AXES: { subject: string; key: keyof RadarValues }[] = [
  { subject: "Comparable Score", key: "reputation" },
  { subject: "Sentiment Score", key: "sentiment" },
  { subject: "Risk Containment", key: "riskContainment" },
  { subject: "Share of Voice", key: "sov" },
];

export function isComplete(v: RadarValues | null): v is RadarValues {
  return !!v && isNum(v.reputation) && isNum(v.sentiment) && isNum(v.riskContainment) && isNum(v.sov);
}

/** Radar rows. A series is only included when ALL four of its values exist, so a missing value can never be drawn as 0. */
export function buildRadarData(clientName: string, client: RadarValues, competitorName: string, competitor: RadarValues | null) {
  const rows: any[] = RADAR_AXES.map(a => ({ subject: a.subject }));
  RADAR_AXES.forEach((a, i) => {
    if (isComplete(client)) rows[i][clientName] = client[a.key];
    if (isComplete(competitor)) rows[i][competitorName] = competitor![a.key];
  });
  return { rows, showClient: isComplete(client), showCompetitor: isComplete(competitor) };
}

export type BarEntry = { name: string; value: number };

/** Bars for a two-entity chart: only entities that have a number get a bar (a missing value is not a 0 bar). */
export function bars(entries: { name: string; value: unknown }[]): BarEntry[] {
  return entries.filter(e => isNum(e.value)).map(e => ({ name: e.name, value: e.value as number }));
}

/** Client share of voice = remainder after every compared competitor; null when nothing is compared yet. */
export function clientShareOfVoice(rows: { sov?: number | null }[] | null | undefined): number | null {
  if (!rows || rows.length === 0) return null;
  const total = rows.reduce((s, r) => s + (isNum(r?.sov) ? (r.sov as number) : 0), 0);
  return Math.max(0, 100 - total);
}

/** Number of entities in the engine's ranking: ranked competitors plus the client (when the client was ranked). */
export function rankedEntityCount(rows: any[] | null | undefined): number {
  const list = rows || [];
  const ranked = list.filter(r => isNum(r?.rank) && r.rank > 0).length;
  const clientRanked = list.length > 0 && isNum(list[0]?.client_rank) ? 1 : 0;
  return ranked + clientRanked;
}

export function rankLabel(rank: unknown, total: number, clientName: string): string {
  if (!isNum(rank) || rank <= 0) return "Unranked";
  return total >= rank ? `#${rank} of ${total} (includes ${clientName})` : `#${rank}`;
}

/** Text of the empty-state card, or null when no card should be shown. */
export function emptyStateMessage(opts: { comparedNames: string[]; searchStatus: string | null | undefined; clientName: string }): { title: string; detail: string } | null {
  if (opts.searchStatus === "searching" || opts.searchStatus === "unpromoted_candidate" || opts.searchStatus === "tracked") return null;
  if (opts.comparedNames.length === 0) {
    return { title: "No tracked competitors yet.", detail: "Search a name above to start tracking a real competitor." };
  }
  return {
    title: `${opts.comparedNames.length} competitor${opts.comparedNames.length === 1 ? " is" : "s are"} being compared with ${opts.clientName}.`,
    detail: `Search one by its exact name above to see the head-to-head: ${opts.comparedNames.join(", ")}.`,
  };
}

export function comparedCompetitorsLabel(n: number, name?: string | null): string {
  return `Across all ${n} compared competitor${n === 1 ? "" : "s"} -- not just ${name || "the one selected above"}`;
}

export function articleCountLabel(n: number): string {
  return `${n} ${n === 1 ? "article" : "articles"}`;
}

export function activityScopeNote(clientName: string): string {
  return `Articles found among the newest ${ACTIVITY_ARTICLE_CAP} about ${clientName}. The scores above use the last 30 days, so this list can differ from what they rest on.`;
}

export function evidenceCaption(mentions: unknown, clientName: string): string | null {
  if (!isNum(mentions)) return null;
  const n = Math.round(mentions);
  return `Based on ${n} mention${n === 1 ? "" : "s"} in the last 30 days (only articles that also mention ${clientName} count).`;
}

export function asOfLabel(iso: unknown): string | null {
  if (typeof iso !== "string" || !iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `As of ${d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" })}`;
}

export function noEvidenceMessage(competitorName: string, clientName: string): string {
  return `No qualifying coverage yet: no article found so far mentions both ${competitorName} and ${clientName}, so there is nothing to score.`;
}

/** Topics hidden from the Topic Ownership chart because the pair has fewer than MIN_TOPIC_COMPARISON_COUNT articles on them in total. */
export function hiddenTopics(entities: { total_documents?: number; topic_counts?: Record<string, number> }[], shownKeys: string[]): string[] {
  const totals: Record<string, number> = {};
  (entities || []).filter(e => e && (e.total_documents ?? 0) > 0).forEach(e => {
    Object.entries(e.topic_counts || {}).forEach(([t, c]) => { totals[t] = (totals[t] || 0) + (c as number); });
  });
  return Object.keys(totals).filter(t => !shownKeys.includes(t)).sort();
}

export function hiddenTopicsNote(hidden: string[]): string | null {
  if (hidden.length === 0) return null;
  return `${hidden.length} topic${hidden.length === 1 ? "" : "s"} with fewer than ${MIN_TOPIC_COMPARISON_COUNT} articles across both entities ${hidden.length === 1 ? "is" : "are"} not shown (${hidden.join(", ")}), so the bars can add up to less than 100%.`;
}

/** True when the score rests on fewer than LOW_EVIDENCE_MENTIONS mentions (display only). Unknown counts are not flagged. */
export function isLowEvidence(mentions: unknown): boolean {
  return isNum(mentions) && Math.round(mentions) < LOW_EVIDENCE_MENTIONS;
}

export function lowEvidenceTitle(): string {
  return `Fewer than ${LOW_EVIDENCE_MENTIONS} mentions in the last 30 days: treat this score as indicative only.`;
}

/** The Risk tile counts only articles that mention the client, so a competitor's own other stories are not in it. */
export function riskTileLabel(clientName: string): string {
  return `Risk in coverage that mentions ${clientName}`;
}

/** Number formatting that never throws on a missing value. */
export function fixed(value: unknown, digits: number): string {
  return isNum(value) ? value.toFixed(digits) : "N/A";
}
