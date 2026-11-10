import { formatDMY } from "./dateFormat";
import { windowPhrase, windowLength } from "./windowText";
// Pure display rules for the Executives page (kept free of React so every sentence can be unit-tested).
//
// Rules: a person with no stored score is "No score yet", never a zero or a grade; under 3 articles the page shows
// "Limited coverage (N articles)" instead of the score and grade (the API still returns both: with so few articles every
// executive with neutral coverage gets the same ~60.2, which says nothing about the person); a row last scored more than 14
// days ago is marked stale with its date. The scoring itself is not touched here.

export const STALE_AFTER_DAYS = 14;
export const LOW_EVIDENCE_DOCS = 3;

const NO_SCORE_STATES = new Set(["INSUFFICIENT_EVIDENCE", "NO_SCORE_YET"]);

export function ageInDays(asOf: string | null | undefined, now: number = Date.now()): number | null {
  if (!asOf) return null;
  const t = new Date(asOf).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((now - t) / 86_400_000));
}

export function isStale(asOf: string | null | undefined, now: number = Date.now()): boolean {
  const d = ageInDays(asOf, now);
  return d !== null && d > STALE_AFTER_DAYS;
}

export function formatAsOfDate(asOf: string | null | undefined): string | null {
  if (!asOf) return null;
  const d = new Date(asOf);
  if (Number.isNaN(d.getTime())) return null;
  return formatDMY(d);
}

export type ExecBadge = "scored" | "low_evidence" | "no_score";

// "Limited coverage: 1 article in 12 months (37 all-time)". The count the score rests on is the one inside the look-back; the all-time count
// is shown beside it so a person with many older articles is not read as unknown. The all-time part is left out when the API did not send it.
export function limitedCoverageText(n: number, windowDaysValue?: unknown, allTime?: unknown): string {
  const inWindow = `${n} article${n === 1 ? "" : "s"} in ${windowLength(windowDaysValue)}`;
  const total = typeof allTime === "number" && Number.isFinite(allTime) && allTime >= 0 ? ` (${allTime} all-time)` : "";
  return `Limited coverage: ${inWindow}${total}`;
}

export interface ExecView {
  badge: ExecBadge;
  scoreText: string;
  gradeText: string;
  hasScore: boolean;
  staleNote: string | null;
  asOfText: string | null;
}

export function executiveView(e: any, now: number = Date.now()): ExecView {
  const asOfText = formatAsOfDate(e?.as_of);
  const staleNote = isStale(e?.as_of, now) && asOfText ? `Stale: last scored ${asOfText}` : null;
  const noScore = !e || typeof e.score !== "number" || NO_SCORE_STATES.has(e.health_status);
  if (noScore) {
    return { badge: "no_score", scoreText: "No score yet", gradeText: "-", hasScore: false, staleNote, asOfText };
  }
  const docs = typeof e.document_count === "number" ? e.document_count : null;
  const scoreText = e.score.toFixed(2);
  if (docs !== null && docs < LOW_EVIDENCE_DOCS) {
    return { badge: "low_evidence", scoreText: limitedCoverageText(docs, e.window_days, e.articles_all_time), gradeText: "-", hasScore: true, staleNote, asOfText };
  }
  return { badge: "scored", scoreText, gradeText: e.grade ?? "-", hasScore: true, staleNote, asOfText };
}

// "Based on 11 documents. Biggest drag: Sentiment (21.4 points lost)."
export function basedOnLine(e: any): string | null {
  if (!e || typeof e.document_count !== "number") return null;
  const n = e.document_count;
  const base = `Based on ${n} document${n === 1 ? "" : "s"}.`;
  const drag = e.biggest_drag;
  if (drag && typeof drag.points_lost === "number" && drag.label) {
    return `${base} Biggest drag on the score: ${drag.label} (${drag.points_lost.toFixed(1)} points lost).`;
  }
  return base;
}

export function eventsLabel(n: number): string {
  return `${n} document${n === 1 ? "" : "s"} behind this score`;
}

export function appearsInLine(clientName: string): string {
  return `Appears in ${clientName} coverage. This does not mean they work for ${clientName}.`;
}

// ---- Default view: the client's top tracked executives -----------------------------------------------------
export const TOP_TRACKED_EXECUTIVES = 8;

// Scored people first (highest score), then people with the most documents, then by name. Never lists candidates.
export function pickTopTrackedExecutives(executives: any[] | null | undefined, limit: number = TOP_TRACKED_EXECUTIVES): any[] {
  const rows = (executives || []).filter(e => e && e.name);
  const scored = (e: any) => typeof e.score === "number" && !NO_SCORE_STATES.has(e.health_status);
  return [...rows]
    .sort((a, b) =>
      (Number(scored(b)) - Number(scored(a)))
      || ((scored(b) ? b.score : 0) - (scored(a) ? a.score : 0))
      || ((b.document_count ?? 0) - (a.document_count ?? 0))
      || a.name.localeCompare(b.name))
    .slice(0, limit);
}

// Why a person has no score: the score looks at one look-back window only (`window_days` from the API, 30 on rows stored before the
// setting existed), so say whether older coverage exists.
// `articles_all_time` / `latest_article_at` come from the API (additive); older payloads fall back to the plain line.
export function noScoreReason(e: any, clientName: string): string {
  const n = typeof e?.articles_all_time === "number" ? e.articles_all_time : null;
  const win = windowPhrase(e?.window_days);
  if (n !== null && n > 0) {
    const newest = typeof e.latest_article_at === "string" ? formatDMY(e.latest_article_at, "") : "";
    return `${n} article${n === 1 ? "" : "s"} mention${n === 1 ? "s" : ""} this person with ${clientName}, but none in the ${win}${newest ? ` (newest ${newest})` : ""}, so there is no score yet.`;
  }
  if (n === 0) return `No article mentions this person together with ${clientName}, so there is nothing to score.`;
  return `No coverage mentioning ${clientName} together with this person in the ${win}.`;
}

export interface TrackedCardView { hasScore: boolean; headline: string; detail: string }

// One card: the score and grade, or a plain sentence saying why there is no score.
export function trackedCardView(e: any, clientName: string, now: number = Date.now()): TrackedCardView {
  const v = executiveView(e, now);
  if (!v.hasScore) {
    return { hasScore: false, headline: "No score yet", detail: noScoreReason(e, clientName) };
  }
  const docs = typeof e.document_count === "number" ? e.document_count : null;
  const limited = v.badge === "low_evidence";
  return {
    hasScore: true,
    headline: limited ? v.scoreText : `${v.scoreText} · grade ${v.gradeText}`,
    detail: `${docs !== null ? `${docs} article${docs === 1 ? "" : "s"} in the ${windowPhrase(e?.window_days)}` : `Scored from the ${windowPhrase(e?.window_days)}`}${v.staleNote ? `. ${v.staleNote}` : ""}`,
  };
}

// Seeded executives only: articles the person's own search returned that do not mention them, so they are not in the score.
// Shown from 3 up; null (not seeded, older payload, or fewer than 3) shows nothing. Never changes a score or grade.
export const FURTHER_ARTICLES_MIN = 3;
export function furtherArticlesLine(e: any): string | null {
  const n = typeof e?.search_hits_uncounted === "number" ? e.search_hits_uncounted : null;
  if (n === null || n < FURTHER_ARTICLES_MIN) return null;
  return `${n} further articles found by search, not counted in the score`;
}

export function noCoverageLine(clientName: string, windowDaysValue?: number | null): string {
  return `Tracked, but no article published in the ${windowPhrase(windowDaysValue)} mentions ${clientName} together with this person, so there is nothing to score yet. Older articles may exist; they are not counted.`;
}

export function notFoundLine(query: string, clientName: string): string {
  return `No tracked executive or discovered candidate matches "${query}" in ${clientName}'s coverage. Only people already found in the coverage can be tracked; try the full name as it appears in articles.`;
}

// ---- Seeded executives: the page opens on them, in role order -----------------------------------------------
export const ALSO_TRACKED_EXECUTIVES = 3;

export interface SeededExecutive { entity_id: string; name: string; rank: number; role?: string | null }

export interface OrderedExecutive {
  row: any;               // the /executives row (a stand-in with no score when the person has no row yet)
  seeded: boolean;
  seedRole: string | null;
  alsoTracked: boolean;   // tracked before seeding (or outside the seeded list) and still shown
  placeholder: boolean;   // seeded, no score row yet
}

// Seeded executives first, in the order the API gives them (role order: chair, MD/CEO, CFO, founders, others), each
// with its stored score row if there is one. After them, up to ALSO_TRACKED_EXECUTIVES other tracked people by the
// existing rule, labelled "also tracked". With no seeded list this is exactly the previous behaviour.
export function orderTrackedExecutives(
  executives: any[] | null | undefined,
  seeded: SeededExecutive[] | null | undefined,
  limit: number = TOP_TRACKED_EXECUTIVES,
): OrderedExecutive[] {
  const rows = (executives || []).filter(e => e && e.name);
  if (!seeded || seeded.length === 0) {
    return pickTopTrackedExecutives(rows, limit).map(row => ({ row, seeded: false, seedRole: null, alsoTracked: false, placeholder: false }));
  }
  const byEntity = new Map<string, any>(rows.filter(r => r.entity_id).map(r => [String(r.entity_id), r]));
  const seededIds = new Set(seeded.map(s => String(s.entity_id)));
  const first: OrderedExecutive[] = [...seeded].sort((a, b) => a.rank - b.rank).map(s => {
    const found = byEntity.get(String(s.entity_id));
    return {
      row: found || { entity_id: s.entity_id, name: s.name, score: null, health_status: "NO_SCORE_YET", document_count: null, articles_all_time: null },
      seeded: true, seedRole: s.role || null, alsoTracked: false, placeholder: !found,
    };
  });
  const rest = pickTopTrackedExecutives(rows.filter(r => !seededIds.has(String(r.entity_id))), ALSO_TRACKED_EXECUTIVES)
    .map(row => ({ row, seeded: false, seedRole: null, alsoTracked: true, placeholder: false }));
  return [...first, ...rest].slice(0, Math.max(limit, first.length + rest.length));
}
