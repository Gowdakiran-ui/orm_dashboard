// Pure logic behind the Risk Center page (RiskTab) and the sidebar's "Highest
// severity flagged". Kept free of React so every number and sentence they state can
// be unit-tested.
//
// Rule for everything here: a missing/failed/loading input yields an explicit
// "unavailable" state, never a believable number or a reassuring default.

import { getRiskLevel, RISK_THRESHOLDS, type RiskLevel } from "./riskLevel";
import { sourceState, type RiskStats } from "./brandEquity";

export type FlaggedLevel = Exclude<RiskLevel, "LOW">;

// Severity of one document. The backend's `risk_level` is the band of the
// UNROUNDED stored score (the same rule the engine stores); the rounded
// `risk` is only used when an older backend did not send it. null = the
// document was never risk-scored.
export function docSeverity(d: any): RiskLevel | null {
  if (!d || d.scored !== true) return null;
  if (d.risk_level === "LOW" || d.risk_level === "MEDIUM" || d.risk_level === "HIGH" || d.risk_level === "CRITICAL") return d.risk_level;
  return typeof d.risk === "number" ? getRiskLevel(d.risk) : null;
}

// Flagged = scored and above the LOW band. Unscored documents are never
// treated as a score of 0 and never flagged.
export function flaggedDocs(documents: any[] | null | undefined): any[] {
  return (documents || [])
    .filter(d => { const s = docSeverity(d); return s !== null && s !== "LOW"; })
    .map(d => ({ ...d, severity: docSeverity(d) as FlaggedLevel }))
    .sort((a, b) => (b.risk_exact ?? b.risk) - (a.risk_exact ?? a.risk));
}

// ---- Confidence ----------------------------------------------------------
// The engine's confidence modifier (0-1): how sure it is about the topic and
// sentiment signals it scored from. NOT a probability that the risk happens.
// null when the item carries no value; never read as 0.
export function confidencePercent(d: any): number | null {
  const c = d?.risk_explainability?.confidence;
  return typeof c === "number" && Number.isFinite(c) ? Math.round(c * 100) : null;
}

export type ConfidenceTier = "LOW" | "MEDIUM" | "HIGH";

export function confidenceTier(pct: number): ConfidenceTier {
  return pct >= 67 ? "HIGH" : pct >= 33 ? "MEDIUM" : "LOW";
}

export const MATRIX_BANDS: FlaggedLevel[] = ["CRITICAL", "HIGH", "MEDIUM"];
export const MATRIX_CONFIDENCE: ConfidenceTier[] = ["LOW", "MEDIUM", "HIGH"];

export interface Matrix {
  grid: Record<FlaggedLevel, Record<ConfidenceTier, any[]>>;
  // Flagged articles that carry no confidence value, so they cannot be placed.
  unplaced: number;
}

// Rows are the platform severity bands (25/50/75), so a document is in the
// same band here as in the table, the tiles and the stored risk_level.
export function buildMatrix(flagged: any[]): Matrix {
  const grid = {} as Matrix["grid"];
  for (const b of MATRIX_BANDS) grid[b] = { LOW: [], MEDIUM: [], HIGH: [] };
  let unplaced = 0;
  for (const d of flagged) {
    const pct = confidencePercent(d);
    if (pct === null) { unplaced++; continue; }
    grid[d.severity as FlaggedLevel][confidenceTier(pct)].push(d);
  }
  return { grid, unplaced };
}

// Deep links from Executive Analytics' SOC matrix still use its own score
// tiers (33/67) and confidence tiers; this keeps that drill-through landing on
// the cell it was clicked from, with the same counts that matrix showed.
function legacyScoreTier(score: number): "LOW" | "MEDIUM" | "HIGH" {
  return score >= 67 ? "HIGH" : score >= 33 ? "MEDIUM" : "LOW";
}

export function legacyCellDocs(flagged: any[], scoreTier: string, conf: string): any[] {
  return flagged.filter(d => {
    const pct = confidencePercent(d);
    return pct !== null && legacyScoreTier(d.risk) === scoreTier && confidenceTier(pct) === conf;
  });
}

// ---- Tiles / sidebar -----------------------------------------------------
export interface RiskCenterTiles {
  flagged: number;
  critical: number;
  high: number;
  medium: number;
  highest: number | null;
  unscored: number;
  asOf: string | null;
}

// Server counts over EVERY visible article (not the 500-article window the
// table is built from). null when the block is missing/malformed.
export function tilesFromSummary(stats: RiskStats | null): RiskCenterTiles | null {
  if (!stats) return null;
  return {
    flagged: stats.total,
    critical: stats.critical,
    high: stats.high,
    medium: stats.medium,
    highest: stats.highest,
    unscored: stats.unscored,
    asOf: stats.asOf,
  };
}

export type SidebarRiskLevel = "UNAVAILABLE" | "NO INCIDENTS" | FlaggedLevel;

// Highest severity band among ALL of the client's flagged articles (no time
// window: the counts go back to the first article collected) -- the same
// data and bands as the Risk Center. Never defaults to a reassuring
// level: loading, errors and a missing block are "UNAVAILABLE".
export function sidebarRiskLevel(loading: boolean | undefined, error: string | null | undefined, stats: RiskStats | null): SidebarRiskLevel {
  if (sourceState(loading, error) !== "ready" || !stats) return "UNAVAILABLE";
  if (stats.critical > 0) return "CRITICAL";
  if (stats.high > 0) return "HIGH";
  if (stats.medium > 0) return "MEDIUM";
  return "NO INCIDENTS";
}

// ---- Wording -------------------------------------------------------------
const LEVEL_WORD: Record<RiskLevel, string> = { LOW: "Low", MEDIUM: "Medium", HIGH: "High", CRITICAL: "Critical" };
export function levelWord(level: RiskLevel): string { return LEVEL_WORD[level]; }

// One plain, deterministic sentence from the stored explainability: no raw
// floats, no engine words. null when the data needed isn't there.
export function reasonSentence(d: any): string | null {
  const sev = docSeverity(d);
  const exp = d?.risk_explainability;
  if (!sev || !exp) return null;
  const score = typeof d.risk_exact === "number" ? d.risk_exact : d.risk;
  if (typeof score !== "number") return null;
  const tone = typeof d.risk_sentiment === "string" ? d.risk_sentiment.toLowerCase() : null;
  const topicWeight = exp.topic_contribution ?? exp.individual_weights?.topic_weight;
  const riskySubject = typeof topicWeight === "number" && topicWeight > 0;
  const parts: string[] = [];
  if (tone) parts.push(`the article's tone is ${tone}`);
  if (riskySubject) parts.push("it covers a high-risk subject");
  if (parts.length === 0) return null;
  return `Flagged because ${parts.join(" and ")}. Rated ${LEVEL_WORD[sev]} (${formatScore(score)}/100).`;
}

// The score as shown to people: one decimal, none for whole numbers. The band
// of a score is decided on the UNROUNDED value (a score of exactly 25 is Low,
// anything above it is Medium), so when one-decimal rounding would land a
// score that is strictly above a band edge ON that edge (25.04 -> "25"), the
// number is shown with two decimals instead (25.04), rounded up if even that
// would land on the edge. The shown number therefore never contradicts its band.
export function formatScore(n: number): string {
  const edges = [RISK_THRESHOLDS.LOW_TO_MEDIUM, RISK_THRESHOLDS.MEDIUM_TO_HIGH, RISK_THRESHOLDS.HIGH_TO_CRITICAL] as number[];
  const one = Math.round(n * 10) / 10;
  if (edges.some(e => n > e && one <= e)) {
    const two = Math.round(n * 100) / 100;
    return (edges.some(e => n > e && two <= e) ? Math.ceil(n * 100) / 100 : two).toString();
  }
  return one.toString();
}

// Published date, or the collected date labelled as such.
export function dateLabel(d: any, locale?: string): { text: string; collected: boolean } {
  if (!d?.timestamp) return { text: "N/A", collected: false };
  const t = new Date(d.timestamp);
  if (Number.isNaN(t.getTime())) return { text: "N/A", collected: false };
  return { text: t.toLocaleString(locale, { dateStyle: "short", timeStyle: "short" }), collected: d.date_basis === "collected" };
}

// ---- Date filter (?date=YYYY-MM-DD, local day) -----------------------------
export function localDateKey(ts: string | null | undefined): string | null {
  if (!ts) return null;
  const t = new Date(ts);
  if (Number.isNaN(t.getTime())) return null;
  const mm = String(t.getMonth() + 1).padStart(2, "0");
  const dd = String(t.getDate()).padStart(2, "0");
  return `${t.getFullYear()}-${mm}-${dd}`;
}

// ---- Window disclosure ---------------------------------------------------
// The table is built from the newest 500 articles; the tiles count all of
// them. Returns the plain sentence to show when the table lists fewer flagged
// articles than the tiles count, else null.
export function windowNote(tableRows: number, flaggedTotal: number | null): string | null {
  if (flaggedTotal === null || tableRows >= flaggedTotal) return null;
  return `Showing the ${tableRows} most recent of ${flaggedTotal} flagged articles.`;
}

export function unscoredNote(unscored: number | null | undefined): string | null {
  if (!unscored || unscored <= 0) return null;
  return `${unscored} article${unscored === 1 ? " has" : "s have"} not been risk-checked yet and ${unscored === 1 ? "is" : "are"} not counted.`;
}
