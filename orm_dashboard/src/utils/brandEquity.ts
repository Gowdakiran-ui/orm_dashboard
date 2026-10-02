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
  dangerCount: number;
  dominantLevel: "CRITICAL" | "HIGH" | "MEDIUM" | "NONE";
  topRiskDocs: { title: string; risk: number }[];
  // Items of coverage that have no risk event at all: not "zero risk", not counted.
  unscored: number;
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
    dangerCount: critical + high,
    dominantLevel: critical > 0 ? "CRITICAL" : high > 0 ? "HIGH" : medium > 0 ? "MEDIUM" : "NONE",
    topRiskDocs: top,
    unscored: n(block.unscored_documents) ?? 0,
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
  kind: "loading" | "unavailable" | "alert" | "danger" | "flagged" | "clear";
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
  advisory: { flagged?: boolean; lead?: string } | null | undefined;
}

// Priority: an open executive alert, then Critical/High documents, then the
// advisory's own flagged lead, else an explicit clear state. No window
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
    .filter(e => typeof e.score === "number")
    .sort((a, b) => (b.score - a.score) || a.name.localeCompare(b.name));
  const highest = scored[0] ?? null;
  const lowest = scored.length > 0 ? scored[scored.length - 1] : null;
  return { total: execs.length, mostMentioned, highest, lowest };
}

export function formatAsOf(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
