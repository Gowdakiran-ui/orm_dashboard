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
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
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
