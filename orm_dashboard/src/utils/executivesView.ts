import { formatDMY } from "./dateFormat";
// Pure display rules for the Executives page (kept free of React so every sentence can be unit-tested).
//
// Rules: a person with no stored score is "No score yet", never a zero or a grade; under 3 documents the
// letter grade is withheld on this page (the API still returns it); a row last scored more than 14 days
// ago is marked stale with its date. The scoring itself is not touched here.

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
    return { badge: "low_evidence", scoreText, gradeText: `Grade withheld: fewer than ${LOW_EVIDENCE_DOCS} documents`, hasScore: true, staleNote, asOfText };
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

export interface TrackedCardView { hasScore: boolean; headline: string; detail: string }

// One card: the score and grade, or a plain sentence saying why there is no score.
export function trackedCardView(e: any, clientName: string, now: number = Date.now()): TrackedCardView {
  const v = executiveView(e, now);
  if (!v.hasScore) {
    return { hasScore: false, headline: "No score yet", detail: `No coverage mentioning ${clientName} together with this person in the last 30 days.` };
  }
  const docs = typeof e.document_count === "number" ? e.document_count : null;
  const grade = v.badge === "low_evidence" ? "grade withheld" : `grade ${v.gradeText}`;
  return {
    hasScore: true,
    headline: `${v.scoreText} · ${grade}`,
    detail: `${docs !== null ? `${docs} article${docs === 1 ? "" : "s"} in the last 30 days` : "Scored from the last 30 days"}${v.staleNote ? `. ${v.staleNote}` : ""}`,
  };
}

export function noCoverageLine(clientName: string): string {
  return `Tracked, but no article published in the last 30 days mentions ${clientName} together with this person, so there is nothing to score yet. Older articles may exist; they are not counted.`;
}

export function notFoundLine(query: string, clientName: string): string {
  return `No tracked executive or discovered candidate matches "${query}" in ${clientName}'s coverage. Only people already found in the coverage can be tracked; try the full name as it appears in articles.`;
}
