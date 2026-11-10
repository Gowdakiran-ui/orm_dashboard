import { formatDMY } from "./dateFormat";
import { windowPhrase } from "./windowText";
// Pure helpers for the Competitors tab (audit/competitors-audit.md F-01, F-02, F-04, F-05, F-06, F-09, F-10, F-12).
// Everything here is plain data in / plain data out so each rule can be tested without rendering the page.

export const ACTIVITY_ARTICLE_CAP = 500; // the page's /documents/client list is the newest 500 articles
export const MIN_TOPIC_COMPARISON_COUNT = 5;
// A competitor with fewer 30-day mentions than this (that also name the client) gets "Not enough coverage" instead of a
// score. Display only: the engine's stored score and rank are not changed. Unknown counts are never treated as low.
export const LOW_EVIDENCE_MENTIONS = 5;

export type RadarValues = { reputation: number | null; sentiment: number | null; riskContainment: number | null; sov: number | null };

export const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

/** A competitor row from competitor-search has no usable numbers when the engine had no evidence. */
export function hasEvidence(c: any): boolean {
  return !!c && c.health_status !== "INSUFFICIENT_EVIDENCE" && isNum(c.reputation_score) && !isLowEvidence(c.mentions_30d);
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

// Competitor scores use the benchmark look-back (BENCHMARK_WINDOW_DAYS = 90). The window the API sent is used when there is one.
export const BENCHMARK_DEFAULT_WINDOW_DAYS = 90;

export function activityScopeNote(clientName: string, windowDaysValue?: unknown): string {
  const days = isNum(windowDaysValue) && windowDaysValue > 0 ? windowDaysValue : BENCHMARK_DEFAULT_WINDOW_DAYS;
  return `Articles found among the newest ${ACTIVITY_ARTICLE_CAP} about ${clientName}. The scores above use the ${windowPhrase(days)}, so this list can differ from what they rest on.`;
}

export function evidenceCaption(mentions: unknown, clientName: string, windowDaysValue?: number | null, seeded: boolean = false): string | null {
  if (!isNum(mentions)) return null;
  const n = Math.round(mentions);
  return seeded
    ? `Based on ${n} mention${n === 1 ? "" : "s"} in the ${windowPhrase(windowDaysValue)} (articles about this competitor itself; they do not need to mention ${clientName}).`
    : `Based on ${n} mention${n === 1 ? "" : "s"} in the ${windowPhrase(windowDaysValue)} (only articles that also mention ${clientName} count).`;
}

export function asOfLabel(iso: unknown): string | null {
  if (typeof iso !== "string" || !iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `As of ${formatDMY(d)}`;
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

/** True when the score would rest on fewer than LOW_EVIDENCE_MENTIONS mentions: no score is shown. Unknown counts are not flagged. */
export function isLowEvidence(mentions: unknown): boolean {
  return isNum(mentions) && Math.round(mentions) < LOW_EVIDENCE_MENTIONS;
}

export function lowEvidenceTitle(windowDaysValue?: number | null): string {
  return `Fewer than ${LOW_EVIDENCE_MENTIONS} mentions in the ${windowPhrase(windowDaysValue)} that also mention the client: not enough coverage to show a score.`;
}

export function notEnoughCoverageMessage(name: string, clientName: string, mentions: unknown, windowDaysValue?: number | null, seeded: boolean = false): string {
  const n = isNum(mentions) ? Math.round(mentions) : 0;
  const together = seeded ? "" : ` together with ${clientName}`;
  return `Not enough coverage: only ${n} mention${n === 1 ? "" : "s"} of ${name}${together} in the ${windowPhrase(windowDaysValue)} (fewer than ${LOW_EVIDENCE_MENTIONS}), so no score is shown.`;
}

/** The Risk tile counts only articles that mention the client, so a competitor's own other stories are not in it. */
export function riskTileLabel(clientName: string): string {
  return `Risk in coverage that mentions ${clientName}`;
}

/** Number formatting that never throws on a missing value. */
export function fixed(value: unknown, digits: number): string {
  return isNum(value) ? value.toFixed(digits) : "N/A";
}


// ---- Competitor cards (the page's opening view) -------------------------------------------------------------
export interface CompetitorCardView {
  name: string;
  hasScore: boolean;
  scoreText: string;          // "83.3 / 100" or "Not enough coverage"
  scoreMeaning: string;
  rankText: string | null;
  sovText: string | null;
  sovMeaning: string | null;
  evidence: string | null;
  thin: boolean;              // fewer than LOW_EVIDENCE_MENTIONS mentions: score shown, with a caution
  thinNote: string | null;
  asOf: string;               // "Data as of 20-10-2026"; every card has one (a card with no date says so)
}

/** One card per compared competitor, built only from the already-served /benchmark row. */
export function competitorCardView(b: any, clientName: string): CompetitorCardView {
  const name = String(b?.competitor_name ?? "Unknown");
  const mentions = isNum(b?.mentions_30d) ? Math.round(b.mentions_30d) : null;
  const lowEvidence = isLowEvidence(b?.mentions_30d);
  const scored = b?.health_status !== "INSUFFICIENT_EVIDENCE" && isNum(b?.reputation) && isNum(b?.rank) && b.rank > 0 && !lowEvidence;
  const asOfIso = typeof b?.as_of === "string" ? b.as_of : null;
  const asOf = asOfIso && formatDMY(asOfIso, "") ? `Data as of ${formatDMY(asOfIso)}` : "Data as of: date not available";
  const thin = false;   // thin evidence no longer shows a caution: below the minimum there is no score at all
  return {
    name,
    hasScore: scored,
    scoreText: scored ? `${(b.reputation as number).toFixed(1)} / 100` : "Not enough coverage",
    scoreMeaning: scored
      ? `How healthy ${name}'s reputation looks in recent articles that also mention ${clientName}. Higher is better; 100 is the best possible.`
      : lowEvidence && (mentions ?? 0) > 0
        ? notEnoughCoverageMessage(name, clientName, mentions, b?.window_days, !!b?.seeded)
        : b?.seeded
          ? `No article from the ${windowPhrase(b?.window_days)} is about ${name}, so no score is shown.`
          : `No article from the ${windowPhrase(b?.window_days)} mentions both ${name} and ${clientName}, so no score is shown.`,
    rankText: scored ? `Ranked #${b.rank} with ${clientName}` : null,
    sovText: isNum(b?.sov) ? `${(b.sov as number).toFixed(1)}% share of voice` : null,
    sovMeaning: isNum(b?.sov) ? `Out of every 100 mentions of ${clientName} and the compared competitors, about ${Math.round(b.sov)} are ${name}.` : null,
    evidence: mentions === null ? null : `Based on ${mentions} mention${mentions === 1 ? "" : "s"} in the ${windowPhrase(b?.window_days)}`,
    thin,
    thinNote: thin ? `Thin evidence: only ${mentions} mention${mentions === 1 ? "" : "s"}, so treat this score with caution.` : null,
    asOf,
  };
}


// ---- Seeded competitors: the page opens on them, in seed order ---------------------------------------------
export interface SeededCompetitor { entity_id: string; name: string; rank: number; context_term?: string | null }

export interface CompetitorCard extends CompetitorCardView {
  key: string;
  entityId: string | null;
  seeded: boolean;
  alsoTracked: boolean;      // tracked outside the seeded list and still shown
  placeholder: boolean;      // seeded, but no benchmark row yet: "Tracked, no coverage yet"
}

/** Card for a seeded competitor that has no benchmark row yet. Never a score, never a zero. */
export function placeholderCardView(name: string, clientName: string): CompetitorCardView {
  return {
    name, hasScore: false, scoreText: "Tracked, no coverage yet",
    scoreMeaning: `${name} is tracked and being searched for, but no article about it has been scored yet, so there is nothing to compare with ${clientName}. It appears here after the next Run Pipeline.`,
    rankText: null, sovText: null, sovMeaning: null, evidence: null, thin: false, thinNote: null, asOf: "Data as of: not scored yet",
  };
}

/** Seeded competitors first in seed order (a card from their /benchmark row, or the placeholder), then every other
 *  compared competitor as "also tracked". With no seeded list this is exactly one card per /benchmark row. */
export function buildCompetitorCards(benchmarks: any[] | null | undefined, seeded: SeededCompetitor[] | null | undefined, clientName: string): CompetitorCard[] {
  const rows = (benchmarks || []).filter(b => b && b.competitor_name);
  const hasSeed = !!seeded && seeded.length > 0;
  if (!hasSeed) {
    return rows.map(b => ({ ...competitorCardView(b, clientName), key: String(b.competitor_id || b.competitor_name), entityId: b.competitor_id ? String(b.competitor_id) : null, seeded: false, alsoTracked: false, placeholder: false }));
  }
  const byEntity = new Map<string, any>(rows.filter(b => b.competitor_id).map(b => [String(b.competitor_id), b]));
  const seededIds = new Set((seeded as SeededCompetitor[]).map(s => String(s.entity_id)));
  const first: CompetitorCard[] = [...(seeded as SeededCompetitor[])].sort((a, b) => a.rank - b.rank).map(s => {
    const row = byEntity.get(String(s.entity_id));
    // A seeded competitor with no row, or a row with no evidence and no mention at all, has nothing to show yet.
    const empty = !row || (row.health_status === "INSUFFICIENT_EVIDENCE" && (!isNum(row.mentions_30d) || Math.round(row.mentions_30d) === 0));
    const view = empty ? placeholderCardView(s.name, clientName) : competitorCardView({ ...row, seeded: true }, clientName);
    return { ...view, key: String(s.entity_id), entityId: String(s.entity_id), seeded: true, alsoTracked: false, placeholder: empty };
  });
  const rest: CompetitorCard[] = rows.filter(b => !seededIds.has(String(b.competitor_id))).map(b => ({
    ...competitorCardView(b, clientName), key: String(b.competitor_id || b.competitor_name), entityId: b.competitor_id ? String(b.competitor_id) : null,
    seeded: false, alsoTracked: true, placeholder: false,
  }));
  return [...first, ...rest];
}
