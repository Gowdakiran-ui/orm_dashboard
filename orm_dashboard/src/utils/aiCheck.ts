// "What AI says about you" card: pure logic (no React) so every sentence and count it states can be unit-tested.
//
// Rule: a missing or malformed payload is "unavailable", never a believable default. Nothing here feeds any score.

export type SourceTier = "high" | "medium" | "low" | "official" | "own" | "user_generated" | "unrated";

export interface AiSource {
  domain: string;
  tier: SourceTier;
  reliability: string;       // "High", "Medium (proposed)", "Low", "Official", "Company", "User-generated", "Unrated"
  lowReliability: boolean;
  // True when the rating is a proposal that still needs team review (the label then ends in "(proposed)").
  proposed: boolean;
  citedInRuns: number;
}

export interface AiPrompt {
  key: string;
  label: string;
  question: string;
  runs: number;
  shortAnswer: string;
  sources: AiSource[];
  stable: boolean | null;    // true = same pages cited in every run, false = pages changed, null = only one run
  stability: string;
}

export interface AiPage {
  url: string;
  title: string | null;
  domain: string;
  tier: SourceTier;
  reliability: string;
  proposed: boolean;
  questions: string[];
  citedInAnswers: number;
}

export interface AiRun {
  id: string;
  status: "running" | "completed" | "stopped_at_cap" | "failed";
  startedAt: string | null;
  finishedAt: string | null;
  costUsd: number;
  estimatedCostUsd: number | null;
  callsOk: number;
  callsFailed: number;
  repeats: number;
  promptCount: number;
  model: string;
  error: string | null;
}

export interface AiEstimate {
  calls: number;
  prompts: number;
  repeats: number;
  estimatedCostUsd: number;
  capUsd: number;
}

export interface AiCheckView {
  enabled: boolean;
  canRun: boolean;
  run: AiRun | null;
  prompts: AiPrompt[];
  lowReliabilityPages: AiPage[];
  // Filled by the server for super admins only.
  removalCandidates: AiPage[];
  estimate: AiEstimate | null;
}

const TIERS: ReadonlySet<string> = new Set(["high", "medium", "low", "official", "own", "user_generated", "unrated"]);
const STATUSES: ReadonlySet<string> = new Set(["running", "completed", "stopped_at_cap", "failed"]);
const str = (v: any): string | null => (typeof v === "string" && v.length > 0 ? v : null);
const num = (v: any): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function parsePage(p: any): AiPage | null {
  const url = str(p?.url), domain = str(p?.domain);
  if (!url || !domain) return null;
  return {
    url, domain, title: str(p.title),
    tier: TIERS.has(p.tier) ? p.tier : "unrated",
    reliability: str(p.reliability) ?? "Unrated",
    proposed: p.proposed === true,
    questions: Array.isArray(p.questions) ? p.questions.filter((q: any) => typeof q === "string") : [],
    citedInAnswers: num(p.cited_in_answers) ?? 1,
  };
}

function parsePrompt(p: any): AiPrompt | null {
  const key = str(p?.key), label = str(p?.label);
  if (!key || !label) return null;
  const sources: AiSource[] = [];
  for (const s of Array.isArray(p.sources) ? p.sources : []) {
    const domain = str(s?.domain);
    if (!domain) continue;
    sources.push({
      domain, tier: TIERS.has(s.tier) ? s.tier : "unrated", reliability: str(s.reliability) ?? "Unrated",
      lowReliability: s.low_reliability === true, proposed: s.proposed === true, citedInRuns: num(s.cited_in_runs) ?? 1,
    });
  }
  return {
    key, label, question: str(p.question) ?? label, runs: num(p.runs) ?? 0, shortAnswer: str(p.short_answer) ?? "",
    sources, stable: p.stable === true ? true : p.stable === false ? false : null, stability: str(p.stability) ?? "",
  };
}

// null when the payload is missing or malformed; { enabled: false } is a valid payload (the feature is switched off).
export function parseAiCheck(payload: any): AiCheckView | null {
  if (!payload || typeof payload !== "object" || typeof payload.enabled !== "boolean") return null;
  const empty: AiCheckView = { enabled: payload.enabled, canRun: false, run: null, prompts: [], lowReliabilityPages: [], removalCandidates: [], estimate: null };
  if (!payload.enabled) return empty;
  const r = payload.run;
  const run: AiRun | null = r && typeof r === "object" && STATUSES.has(r.status) && str(r.id)
    ? {
        id: r.id, status: r.status, startedAt: str(r.started_at), finishedAt: str(r.finished_at), costUsd: num(r.cost_usd) ?? 0,
        estimatedCostUsd: num(r.estimated_cost_usd), callsOk: num(r.calls_ok) ?? 0, callsFailed: num(r.calls_failed) ?? 0,
        repeats: num(r.repeats) ?? 0, promptCount: num(r.prompt_count) ?? 0, model: str(r.model) ?? "", error: str(r.error),
      }
    : null;
  const e = payload.estimate;
  const estimate: AiEstimate | null = e && num(e.calls) !== null && num(e.estimated_cost_usd) !== null
    ? { calls: e.calls, prompts: num(e.prompts) ?? 0, repeats: num(e.repeats) ?? 0, estimatedCostUsd: e.estimated_cost_usd, capUsd: num(e.cap_usd) ?? 0 }
    : null;
  const pages = (a: any) => (Array.isArray(a) ? a.map(parsePage).filter((x): x is AiPage => x !== null) : []);
  return {
    enabled: true,
    canRun: payload.can_run === true,
    run,
    prompts: Array.isArray(payload.prompts) ? payload.prompts.map(parsePrompt).filter((x: AiPrompt | null): x is AiPrompt => x !== null) : [],
    lowReliabilityPages: pages(payload.low_reliability_pages),
    removalCandidates: pages(payload.removal_candidates),
    estimate,
  };
}

export function formatUsd(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? `$${n.toFixed(2)}` : "unknown";
}

// "Run AI check" confirmation text: the estimate is shown before anything is asked.
export function estimateSentence(e: AiEstimate | null): string {
  if (!e) return "The cost estimate is unavailable.";
  return `${e.prompts} questions asked ${e.repeats} times = ${e.calls} paid web searches, about ${formatUsd(e.estimatedCostUsd)} (it stops before ${formatUsd(e.capUsd)}).`;
}

export function runLine(run: AiRun | null): string {
  if (!run) return "No AI check has been run for this company yet.";
  if (run.status === "running") return `Running… ${run.callsOk} of ${run.promptCount * run.repeats} answers so far.`;
  if (run.status === "failed") return `The last AI check failed${run.callsOk ? ` after ${run.callsOk} answers` : ""}${run.error ? `: ${run.error}` : "."}`;
  const when = run.finishedAt ?? run.startedAt;
  const date = when ? new Date(when) : null;
  const dateText = date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : null;
  const partial = run.status === "stopped_at_cap" ? " Stopped early at the cost limit." : "";
  return `${run.callsOk} answers${dateText ? ` · ${dateText}` : ""} · cost ${formatUsd(run.costUsd)}.${partial}`;
}

// Stability marker wording and tone for one question.
export function stabilityTone(p: Pick<AiPrompt, "stable">): "same" | "varies" | "unknown" {
  return p.stable === true ? "same" : p.stable === false ? "varies" : "unknown";
}

export function lowReliabilityCount(view: AiCheckView): number {
  return view.lowReliabilityPages.length;
}

// The internal list shows "Low reliability" and "User-generated" pages by default. Pages from outlets the platform has no
// trust decision for ("Unrated") are not listed until someone opens them: they are a rating to-do, not a finding.
export interface RemovalGroup {
  key: "low" | "user_generated" | "unrated";
  label: string;
  pages: AiPage[];
  collapsed: boolean;
}

export function groupRemovalCandidates(pages: AiPage[]): RemovalGroup[] {
  const groups: RemovalGroup[] = [
    { key: "low", label: "Low reliability", pages: pages.filter(p => p.tier === "low"), collapsed: false },
    { key: "user_generated", label: "User-generated", pages: pages.filter(p => p.tier === "user_generated"), collapsed: false },
    { key: "unrated", label: "Unrated", pages: pages.filter(p => p.tier === "unrated"), collapsed: true },
  ];
  return groups.filter(g => g.pages.length > 0);
}

// The collapsed line for unrated pages.
export function unratedLine(n: number): string {
  return `${n} cited ${n === 1 ? "page is" : "pages are"} unrated and ${n === 1 ? "needs" : "need"} a rating`;
}

export const PROPOSED_RATING_NOTE = "Proposed rating, needs team review.";

// Fixed wording of the internal list. It never says content can be removed: that is a legal decision.
export const REMOVAL_LIST_TITLE = "Possible removal candidates";
export const REMOVAL_LIST_NOTICE =
  "Internal only. Pages that AI answers cited from low-reliability outlets. Whether any takedown request is possible for these pages is a legal question: " +
  "each page needs legal review before anything is requested. This list does not say any page can be removed.";
export const CARD_NOTICE =
  "Answers from an AI search tool (Claude Haiku 4.5 with web search), asked each question three times. This is a check on what AI " +
  "tools may say, not a score: it changes no score, risk or alert.";
