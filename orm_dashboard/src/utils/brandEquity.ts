import { decodeHtmlEntities } from "@/lib/utils";

// Pure logic behind the Brand Equity page (ReputationSummaryCard). Kept free of
// React so every number and sentence the page states can be unit-tested.
//
// Rule for everything here: a missing/failed/loading input yields an explicit
// "unavailable"/"loading" state, never a believable number.

export type SourceState = "loading" | "error" | "ready";

export function sourceState(loading?: boolean, error?: string | null): SourceState {
  if (loading) return "loading";
  if (error) return "error";
  return "ready";
}

export interface RiskStats {
  total: number;
  critical: number;
  high: number;
  medium: number;
  avg: number | null;
  // Highest whole-number score among flagged documents; null when none.
  highest: number | null;
  // When the newest of these scores was computed (ISO), if known.
  asOf: string | null;
  dangerCount: number;
  dominantLevel: "CRITICAL" | "HIGH" | "MEDIUM" | "NONE";
  topRiskDocs: { title: string; risk: number }[];
  // Items of coverage that have no risk event at all: not "zero risk", not counted.
  unscored: number;
  // Items that DO carry a risk score (the server's scored_documents); null when an older payload does not send it.
  // 0 means nothing has been risk-scored yet, which is "no data", not "no risk".
  scored: number | null;
}

// Reads the server-computed `document_risk` block of /reputation-summary
// (counts over EVERY visible document, per document, above the Low band).
// Returns null when the block is missing or malformed so the page can say
// "unavailable" instead of showing zeros.
export function riskStatsFromSummary(block: any): RiskStats | null {
  if (!block || typeof block !== "object") return null;
  const n = (v: any) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const total = n(block.total), critical = n(block.critical), high = n(block.high), medium = n(block.medium);
  if (total === null || critical === null || high === null || medium === null) return null;
  const top = Array.isArray(block.top)
    ? block.top.filter((t: any) => t && typeof t.title === "string" && typeof t.risk === "number").slice(0, 2)
    : [];
  return {
    total, critical, high, medium,
    avg: n(block.average),
    highest: n(block.highest),
    asOf: typeof block.as_of === "string" ? block.as_of : null,
    dangerCount: critical + high,
    dominantLevel: critical > 0 ? "CRITICAL" : high > 0 ? "HIGH" : medium > 0 ? "MEDIUM" : "NONE",
    topRiskDocs: top,
    unscored: n(block.unscored_documents) ?? 0,
    scored: n(block.scored_documents),
  };
}

// The engine ranks the client and every evidenced competitor together; the
// top competitor is the lowest positive rank, ties broken by name. Rows with
// rank 0 (no evidence) are never "top".
export function pickTopCompetitor(benchmarks: any[] | null | undefined): any | null {
  const ranked = (benchmarks || []).filter(b => b && typeof b.rank === "number" && b.rank > 0 && b.competitor_name);
  if (ranked.length === 0) return null;
  ranked.sort((a, b) => (a.rank - b.rank) || String(a.competitor_name).localeCompare(String(b.competitor_name)));
  return ranked[0];
}

export interface CompetitiveStanding {
  state: SourceState | "empty";
  rank: number | null;
  shareOfVoice: number | null;
  topCompetitor: string | null;
}

// Share of voice and rank are the benchmark engine's own figures for its
// latest run (client_share_of_voice / client_rank on every /benchmark row).
export function computeCompetitiveStanding(
  benchmarks: any[] | null | undefined,
  loading?: boolean,
  error?: string | null
): CompetitiveStanding {
  const st = sourceState(loading, error);
  if (st !== "ready") return { state: st, rank: null, shareOfVoice: null, topCompetitor: null };
  const rows = (benchmarks || []).filter(b => b && b.competitor_name);
  if (rows.length === 0) return { state: "empty", rank: null, shareOfVoice: null, topCompetitor: null };
  const first = rows[0];
  return {
    state: "ready",
    rank: typeof first.client_rank === "number" ? first.client_rank : null,
    shareOfVoice: typeof first.client_share_of_voice === "number" ? first.client_share_of_voice : null,
    topCompetitor: pickTopCompetitor(rows)?.competitor_name ?? null,
  };
}

export interface Verdict {
  kind: "loading" | "unavailable" | "alert" | "danger" | "flagged" | "nodata" | "clear";
  emoji: string;
  text: string;
  action: "risk" | null;
  actionLabel: string | null;
}

export interface VerdictInput {
  riskState: SourceState;
  advisoryState: SourceState;
  execAlert: { open: boolean; alert?: { entity_name?: string | null; severity?: string | null } | null };
  dangerCount: number;
  totalRisks: number;
  // How many articles carry a risk score at all (RiskStats.scored). 0 = nothing scored yet; null/undefined = not known.
  scoredDocuments?: number | null;
  advisory: { flagged?: boolean; lead?: string } | null | undefined;
}

// Priority: an open executive alert, then Critical/High documents, then the
// advisory's own flagged lead, then "not enough data" when no article has been risk-scored, else an explicit clear state. No window
// ("this week") or stability claim is made: none is computed anywhere.
export function computeVerdict(i: VerdictInput): Verdict {
  if (i.riskState === "loading" || i.advisoryState === "loading") {
    return { kind: "loading", emoji: "⏳", text: "Checking current risk activity…", action: null, actionLabel: null };
  }
  if (i.riskState === "error" || i.advisoryState === "error") {
    return { kind: "unavailable", emoji: "⚪", text: "Risk status is unavailable right now.", action: null, actionLabel: null };
  }
  if (i.execAlert.open) {
    const name = i.execAlert.alert?.entity_name ?? "an executive";
    const sev = i.execAlert.alert?.severity;
    return {
      kind: "alert",
      emoji: sev === "CRITICAL" ? "🔴" : "🟡",
      text: `An open executive-risk alert needs your attention — ${name}${sev ? ` (${sev})` : ""}.`,
      action: "risk",
      actionLabel: "See what it's about →",
    };
  }
  if (i.dangerCount > 0) {
    return {
      kind: "danger",
      emoji: "🟡",
      text: `${i.dangerCount} risk${i.dangerCount === 1 ? "" : "s"} flagged as Critical or High.`,
      action: "risk",
      actionLabel: "See what it's about →",
    };
  }
  if (i.advisory?.flagged === true && i.advisory.lead) {
    return { kind: "flagged", emoji: "🟡", text: i.advisory.lead, action: null, actionLabel: null };
  }
  // Nothing risk-scored yet (new client, or every article still unscored): "no risks" would be a claim nobody has checked.
  if (i.scoredDocuments === 0) {
    return { kind: "nodata", emoji: "⚪", text: "Not enough data yet", action: null, actionLabel: null };
  }
  return {
    kind: "clear",
    emoji: "🟢",
    text: `No Critical or High risks flagged. Watching ${i.totalRisks} tracked risk${i.totalRisks === 1 ? "" : "s"}.`,
    action: null,
    actionLabel: null,
  };
}

export interface ExecStats {
  total: number;
  mostMentioned: string | null;
  highest: any | null;
  lowest: any | null;
}

// Executives: most-mentioned by real document_count (name tiebreak); highest /
// lowest by the executive's composite reputation score. Entries without a
// numeric score are left out of the score comparison rather than read as 0.
export function computeExecStats(executives: any[] | null | undefined): ExecStats {
  const execs = (executives || []).filter(e => e && e.name);
  const mostMentioned = [...execs]
    .filter(e => typeof e.document_count === "number")
    .sort((a, b) => (b.document_count - a.document_count) || a.name.localeCompare(b.name))[0]?.name ?? null;
  const scored = execs
    // A person with no evidence is stored as score 0.0 / grade "NA"; that is "no score", not a real zero.
    .filter(e => typeof e.score === "number" && e.health_status !== "INSUFFICIENT_EVIDENCE")
    .sort((a, b) => (b.score - a.score) || a.name.localeCompare(b.name));
  const highest = scored[0] ?? null;
  const lowest = scored.length > 0 ? scored[scored.length - 1] : null;
  return { total: execs.length, mostMentioned, highest, lowest };
}

// The one rule for "is there a reputation score to show": the summary's reputation block says
// status "ok" and carries a numeric score. Anything else (no_data, insufficient_evidence, missing
// block) is "N/A", never a zero. Brand Equity and Executive Analytics both read this.
export interface ReputationBlock { status?: string; score?: number | null; grade?: string | null; computed_at?: string | null }

export function isReputationScoreKnown(rep: ReputationBlock | null | undefined): boolean {
  return !!rep && rep.status === "ok" && typeof rep.score === "number";
}

export function formatReputationScore(rep: ReputationBlock | null | undefined): string {
  return rep && isReputationScoreKnown(rep) ? (rep.score as number).toFixed(2) : "N/A";
}

export function formatAsOf(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// ---- Brand Equity page view ------------------------------------------------
// Everything the Brand Equity page (ReputationSummaryCard) states in words or numbers, built in one
// place so the page and the exported report read the same function. Pure: no React, no clock.
export const UNAVAILABLE_TEXT = "Unavailable";

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

// The parts of /reputation-summary and /plan-advisory the Brand Equity page reads.
export interface ReputationSummaryLike {
  reputation?: ReputationBlock | null;
  document_risk?: unknown;
  sentiment?: { positive: number; neutral: number; negative: number; dominant: string | null } | null;
  executive_alert?: { open: boolean; alert?: { entity_name?: string | null; severity?: string | null } | null } | null;
}

export interface BrandEquityViewInput {
  reputationSummary: ReputationSummaryLike | null | undefined;
  planAdvisory?: { flagged?: boolean; lead?: string } | null;
  planAdvisoryLoading?: boolean;
  planAdvisoryError?: string | null;
  executives: unknown[];
  executivesLoading?: boolean;
  executivesError?: string | null;
  activeClientName: string;
  normalizedBenchmarks?: unknown[];
  benchmarksLoading?: boolean;
  benchmarksError?: string | null;
  // How a stored ISO timestamp is shown: the page uses the viewer's locale (formatAsOf), the report uses IST.
  formatDate?: (iso: string | null | undefined) => string | null;
}

// The Risk Profile paragraph. The average score is its own part because the page makes it a link.
export type RiskProfileText =
  | { kind: "unavailable"; text: string }
  | { kind: "none"; text: string }
  | { kind: "some"; before: string; avg: string; after: string };

export function buildBrandEquityView(i: BrandEquityViewInput) {
  const name = i.activeClientName;
  const formatDate = i.formatDate ?? formatAsOf;
  const execState = sourceState(i.executivesLoading, i.executivesError);
  // plan-advisory resolved without an error but with no payload is a failure too.
  const advisoryState = sourceState(
    i.planAdvisoryLoading,
    i.planAdvisoryError || (!i.planAdvisoryLoading && !i.planAdvisory ? "No data" : null)
  );
  const riskStats = riskStatsFromSummary(i.reputationSummary?.document_risk);
  const execStats = computeExecStats(i.executives);
  const standing = computeCompetitiveStanding(i.normalizedBenchmarks ?? [], i.benchmarksLoading, i.benchmarksError);

  const rep = i.reputationSummary?.reputation || {};
  const sentiment = i.reputationSummary?.sentiment || { positive: 0, neutral: 0, negative: 0, dominant: null };
  const execAlert = i.reputationSummary?.executive_alert || { open: false, alert: null };
  const riskState: SourceState = riskStats ? "ready" : "error";

  const scoreKnown = isReputationScoreKnown(rep);
  const scoreDisplay = formatReputationScore(rep);
  const gradeDisplay = scoreKnown ? (rep.grade ?? "N/A") : "N/A";
  const asOf = formatDate(rep.computed_at);
  const scoreStatusText = scoreKnown
    ? ""
    : rep.status === "insufficient_evidence"
    ? "Not enough evidence to score yet"
    : "No score computed yet";

  const alertNames = execAlert.open && execAlert.alert?.entity_name ? execAlert.alert.entity_name : null;
  const alertLine = execAlert.open
    ? `1 open executive-risk alert: ${alertNames ?? "unknown"}.`
    : "No open executive-risk alerts.";

  // One-line verdict promoted from content that exists further down this page.
  const verdict = computeVerdict({
    riskState,
    advisoryState,
    execAlert,
    dangerCount: riskStats?.dangerCount ?? 0,
    totalRisks: riskStats?.total ?? 0,
    scoredDocuments: riskStats?.scored ?? null,
    advisory: i.planAdvisory,
  });

  const overviewText = scoreKnown
    ? `${name}'s reputation score is ${scoreDisplay} (${gradeDisplay})${asOf ? `, as of ${asOf}` : ""}.`
    : rep.status === "insufficient_evidence"
    ? `There is not enough evidence yet to compute a reputation score for ${name}.`
    : `No reputation score has been computed yet for ${name}.`;

  const uncheckedText = riskStats && riskStats.unscored > 0
    ? ` ${riskStats.unscored} ${plural(riskStats.unscored, "item has", "items have")} not been risk-checked yet and ${plural(riskStats.unscored, "is", "are")} not counted.`
    : "";

  const topTitle = (k: number) => decodeHtmlEntities(riskStats!.topRiskDocs[k].title);
  const riskProfile: RiskProfileText = !riskStats
    ? { kind: "unavailable", text: "Risk figures are unavailable." }
    : riskStats.total === 0
    ? { kind: "none", text: `No items of coverage carry a risk above Low.${uncheckedText}` }
    : {
        kind: "some",
        before: `${riskStats.total} ${plural(riskStats.total, "item of coverage carries", "items of coverage carry")} a risk above Low (${riskStats.critical} critical, ${riskStats.high} high, ${riskStats.medium} medium), with an average risk score of `,
        avg: riskStats.avg !== null ? String(Math.round(riskStats.avg)) : UNAVAILABLE_TEXT,
        after: "." +
          (riskStats.topRiskDocs.length > 0
            ? ` The highest-risk item is "${topTitle(0)}" (${Math.round(riskStats.topRiskDocs[0].risk)} pts)` +
              (riskStats.topRiskDocs[1] ? `, followed by "${topTitle(1)}" (${Math.round(riskStats.topRiskDocs[1].risk)} pts).` : ".")
            : "") +
          uncheckedText,
      };

  const sentimentText = (() => {
    const counts = `${sentiment.positive} positive, ${sentiment.neutral} neutral and ${sentiment.negative} negative mentions`;
    if (!sentiment.dominant) return `No mentions of ${name} with a sentiment reading yet.`;
    if (sentiment.dominant === "mixed") return `Coverage about ${name} is evenly split between its two most common tones: ${counts}.`;
    return `Coverage about ${name} is mostly ${sentiment.dominant}: ${counts}.`;
  })();

  const peopleText: string | null = (() => {
    if (execState === "loading") return "Loading notable people…";
    if (execState === "error") return "Notable-people data is unavailable.";
    return (execStats.mostMentioned
      ? `${execStats.mostMentioned} is the most-mentioned person, out of ${execStats.total} notable people tracked in ${name}'s coverage (not necessarily ${name}'s own staff).`
      : `No notable people have been tracked yet in ${name}'s coverage.`) +
      (execStats.highest && execStats.lowest && execStats.highest !== execStats.lowest
        ? ` ${execStats.highest.name} has the highest reputation score among them (${execStats.highest.score.toFixed(1)}), while ${execStats.lowest.name} has the lowest (${execStats.lowest.score.toFixed(1)}).`
        : "");
  })();

  const standingText = (() => {
    if (standing.state === "loading") return "Loading competitive standing…";
    if (standing.state === "error") return "Competitive standing is unavailable.";
    if (standing.state === "empty") return "No competitor comparison available yet.";
    const rankPart = standing.rank !== null
      ? `${name} ranks #${standing.rank} among the competitors found in coverage.`
      : `${name} could not be ranked against competitors yet (not enough evidence).`;
    const sovPart = standing.shareOfVoice !== null
      ? ` ${name} accounts for ${standing.shareOfVoice.toFixed(1)}% of all mentions of ${name} and the tracked competitors over the last 30 days (share of voice).`
      : "";
    return `${rankPart}${sovPart}${standing.topCompetitor ? ` The top-ranked competitor is ${standing.topCompetitor}.` : ""}`;
  })();

  return {
    execState, advisoryState, riskState, riskStats, execStats, standing,
    rep, sentiment, execAlert,
    scoreKnown, scoreDisplay, gradeDisplay, asOf, scoreStatusText,
    verdict, alertLine, overviewText, uncheckedText, riskProfile, sentimentText, peopleText, standingText,
  };
}
