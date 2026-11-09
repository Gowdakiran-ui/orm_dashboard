// Run Pipeline cost meter, shown to super admins only. Pure logic (no React) so every figure and sentence can be unit-tested.
//
// Rule: a missing or malformed payload is "unavailable", never a believable zero. Apify figures are exact for Reddit and
// estimated for Instagram; the LLM dollar figure is an estimate from token counts at public per-token prices.

export interface CostBreakdownRow {
  key: string;
  calls: number;
  usd: number | null;       // null when the cost is not known
  estimated: boolean;
  note: string | null;
}

export interface PipelineCostView {
  runId: string;
  finalized: boolean;
  run: { status: string; stage: string | null; startedAt: string | null; finishedAt: string | null; durationS: number | null } | null;
  apify: { calls: number; costUsd: number; estimated: boolean; rows: CostBreakdownRow[] };
  llm: { calls: number; tokensPrompt: number; tokensCompletion: number; estCostUsd: number; rows: CostBreakdownRow[] };
  search: { calls: number; rows: { key: string; calls: number }[] };
  totalUsd: number;
}

export type PipelineCostState = { state: "ready"; cost: PipelineCostView } | { state: "empty" } | { state: "unavailable" };

const num = (v: any): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: any): string | null => (typeof v === "string" && v.length > 0 ? v : null);

export function parsePipelineCost(payload: any): PipelineCostState {
  if (!payload || typeof payload !== "object" || !("last_run" in payload)) return { state: "unavailable" };
  const r = payload.last_run;
  if (r === null) return { state: "empty" };
  if (!r || typeof r !== "object" || !str(r.run_id)) return { state: "unavailable" };
  const a = r.apify, l = r.llm, s = r.search;
  const total = num(r.total_usd);
  if (!a || !l || !s || total === null || num(a.calls) === null || num(a.cost_usd) === null || num(l.calls) === null || num(l.est_cost_usd) === null || num(s.calls) === null) {
    return { state: "unavailable" };
  }
  const apifyRows: CostBreakdownRow[] = Object.entries(a.by_source || {}).map(([key, v]: [string, any]) => ({
    key, calls: num(v?.calls) ?? 0, usd: num(v?.usd), estimated: v?.estimated === true,
    note: v?.estimated === true ? "estimated" : "reported by Apify",
  }));
  const llmRows: CostBreakdownRow[] = Object.entries(l.by_type || {}).map(([key, v]: [string, any]) => {
    const known = v?.price_known !== false;
    return { key, calls: num(v?.calls) ?? 0, usd: known ? num(v?.est_usd) : null, estimated: true, note: known ? (str(v?.model) ?? "estimated") : "no price listed, not costed" };
  });
  const run = r.run && typeof r.run === "object"
    ? { status: str(r.run.status) ?? "UNKNOWN", stage: str(r.run.stage), startedAt: str(r.run.started_at), finishedAt: str(r.run.finished_at), durationS: num(r.run.duration_s) }
    : null;
  return {
    state: "ready",
    cost: {
      runId: r.run_id, finalized: r.finalized === true, run,
      apify: { calls: a.calls, costUsd: a.cost_usd, estimated: a.estimated === true, rows: apifyRows },
      llm: { calls: l.calls, tokensPrompt: num(l.tokens_prompt) ?? 0, tokensCompletion: num(l.tokens_completion) ?? 0, estCostUsd: l.est_cost_usd, rows: llmRows },
      search: { calls: s.calls, rows: Object.entries(s.by_source || {}).map(([key, n]) => ({ key, calls: num(n) ?? 0 })) },
      totalUsd: total,
    },
  };
}

// Dollars with the precision a small cost needs: $0.0123, $1.25.
export function formatCost(n: number | null | undefined): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "unknown";
  return n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`;
}

export function apifyLine(c: PipelineCostView): string {
  if (c.apify.calls === 0) return "No Apify call in this run.";
  return `${c.apify.calls} ${c.apify.calls === 1 ? "call" : "calls"}, ${formatCost(c.apify.costUsd)}${c.apify.estimated ? " (partly estimated)" : " (reported by Apify)"}`;
}

export function llmLine(c: PipelineCostView): string {
  if (c.llm.calls === 0) return "No LLM call in this run.";
  return `${c.llm.calls} ${c.llm.calls === 1 ? "call" : "calls"}, ${c.llm.tokensPrompt.toLocaleString("en-GB")} tokens in, ${c.llm.tokensCompletion.toLocaleString("en-GB")} out, about ${formatCost(c.llm.estCostUsd)} (estimated)`;
}

export function searchLine(c: PipelineCostView): string {
  if (c.search.calls === 0) return "No keyword search in this run.";
  return `${c.search.calls} keyword ${c.search.calls === 1 ? "search" : "searches"}${c.search.rows.length ? ` (${c.search.rows.map(r => `${r.key} ${r.calls}`).join(", ")})` : ""}`;
}

export function runLine(c: PipelineCostView): string {
  const run = c.run;
  if (!run) return `Run ${c.runId.slice(0, 8)}.`;
  const when = run.finishedAt ?? run.startedAt;
  const d = when ? new Date(when) : null;
  const date = d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : null;
  const dur = run.durationS !== null ? `${Math.round(run.durationS)} s` : null;
  return [`Run ${c.runId.slice(0, 8)}`, run.status.toLowerCase(), date, dur].filter(Boolean).join(" · ") + (c.finalized ? "." : ". Still counting: the run has not finished.");
}

export const PIPELINE_COST_NOTE =
  "Super admins only. Apify is the actor's own reported usage for Reddit and an estimate for Instagram (results x $0.0027). The LLM figure is an " +
  "estimate from token counts at public per-token prices and includes any LLM call for this company during the run's time window. It changes no score.";
