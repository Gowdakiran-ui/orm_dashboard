import { describe, it, expect } from "vitest";
import { parseAiCheck, groupRemovalCandidates, estimateSentence, runLine, stabilityTone, REMOVAL_LIST_NOTICE, REMOVAL_LIST_TITLE, CARD_NOTICE, formatUsd } from "./aiCheck";

const page = (over: any = {}) => ({ url: "https://www.inventiva.co.in/story", title: "A story", domain: "inventiva.co.in", tier: "low", reliability: "Low", questions: ["Is it trustworthy?"], cited_in_answers: 4, ...over });
const prompt = (over: any = {}) => ({
  key: "trustworthy", label: "Is it trustworthy?", question: "Is Acme a trustworthy company?", runs: 3, short_answer: "Mixed picture.",
  sources: [{ domain: "livemint.com", tier: "high", reliability: "High", low_reliability: false, cited_in_runs: 3 }, { domain: "inventiva.co.in", tier: "low", reliability: "Low", low_reliability: true, cited_in_runs: 2 }],
  stable: true, stability: "Same pages cited in all 3 runs.", ...over,
});
const payload = (over: any = {}) => ({
  enabled: true, can_run: true,
  run: { id: "r1", status: "completed", started_at: "2026-11-07T10:00:00+00:00", finished_at: "2026-11-07T10:03:00+00:00", cost_usd: 0.31, estimated_cost_usd: 0.324, calls_ok: 24, calls_failed: 0, repeats: 3, prompt_count: 8, model: "anthropic/claude-haiku-4.5", error: null },
  prompts: [prompt()], low_reliability_pages: [page()], removal_candidates: [page()],
  estimate: { calls: 24, prompts: 8, repeats: 3, estimated_cost_usd: 0.324, cap_usd: 0.6 }, ...over,
});

describe("parseAiCheck", () => {
  it("reads a full payload", () => {
    const v = parseAiCheck(payload())!;
    expect(v).toMatchObject({ enabled: true, canRun: true });
    expect(v.run).toMatchObject({ status: "completed", callsOk: 24, costUsd: 0.31 });
    expect(v.prompts[0]).toMatchObject({ key: "trustworthy", stable: true, shortAnswer: "Mixed picture." });
    expect(v.prompts[0].sources.map(s => [s.domain, s.reliability, s.lowReliability])).toEqual([["livemint.com", "High", false], ["inventiva.co.in", "Low", true]]);
    expect(v.lowReliabilityPages[0]).toMatchObject({ domain: "inventiva.co.in", citedInAnswers: 4 });
    expect(v.removalCandidates).toHaveLength(1);
  });

  it("the switched-off payload is valid and empty; a missing or malformed payload is null", () => {
    expect(parseAiCheck({ enabled: false })).toMatchObject({ enabled: false, prompts: [], run: null });
    expect(parseAiCheck(null)).toBeNull();
    expect(parseAiCheck({})).toBeNull();
    expect(parseAiCheck({ enabled: "yes" })).toBeNull();
  });

  it("drops malformed prompts, sources and pages instead of inventing values; unknown tiers read as unrated", () => {
    const v = parseAiCheck(payload({
      prompts: [prompt(), { label: "no key" }, prompt({ key: "x", sources: [{ tier: "high" }, { domain: "d.com", tier: "weird" }] })],
      low_reliability_pages: [page(), { domain: "x.com" }, page({ url: "https://q.com/a", tier: "nope" })],
    }))!;
    expect(v.prompts.map(p => p.key)).toEqual(["trustworthy", "x"]);
    expect(v.prompts[1].sources).toEqual([expect.objectContaining({ domain: "d.com", tier: "unrated" })]);
    expect(v.lowReliabilityPages.map(p => p.tier)).toEqual(["low", "unrated"]);
  });

  it("an unknown run status means no run, and stability is null when unknown", () => {
    expect(parseAiCheck(payload({ run: { id: "r", status: "weird" } }))!.run).toBeNull();
    expect(parseAiCheck(payload({ prompts: [prompt({ stable: null })] }))!.prompts[0].stable).toBeNull();
  });

  it("a non-admin payload carries no removal candidates and cannot run", () => {
    const v = parseAiCheck(payload({ can_run: false, removal_candidates: [] }))!;
    expect(v.canRun).toBe(false);
    expect(v.removalCandidates).toEqual([]);
  });
});

describe("removal candidates are grouped, with unrated outlets on their own", () => {
  const p = (tier: string, reliability: string, url: string) => ({ ...page({ tier, reliability, url, domain: new URL(url).hostname }) });
  it("splits low / user-generated from unrated and never mixes them", () => {
    const v = parseAiCheck(payload({ removal_candidates: [
      p("low", "Low", "https://inventiva.co.in/a"), p("unrated", "Unrated", "https://squaremind.in/b"),
      p("user_generated", "User-generated", "https://quora.com/c"), p("unrated", "Unrated", "https://propreport.in/d"),
    ] }))!;
    const g = groupRemovalCandidates(v.removalCandidates);
    expect(g.map(x => [x.key, x.label, x.pages.map(y => y.domain)])).toEqual([
      ["low", "Low reliability", ["inventiva.co.in", "quora.com"]],
      ["unrated", "Unrated", ["squaremind.in", "propreport.in"]],
    ]);
  });
  it("leaves out an empty group, and returns nothing for an empty list", () => {
    expect(groupRemovalCandidates(parseAiCheck(payload({ removal_candidates: [p("unrated", "Unrated", "https://x.in/a")] }))!.removalCandidates).map(x => x.key)).toEqual(["unrated"]);
    expect(groupRemovalCandidates(parseAiCheck(payload({ removal_candidates: [p("low", "Low", "https://x.in/a")] }))!.removalCandidates).map(x => x.key)).toEqual(["low"]);
    expect(groupRemovalCandidates([])).toEqual([]);
  });
});

describe("wording", () => {
  it("prints the estimate before running", () => {
    expect(estimateSentence({ calls: 24, prompts: 8, repeats: 3, estimatedCostUsd: 0.324, capUsd: 0.6 }))
      .toBe("8 questions asked 3 times = 24 paid web searches, about $0.32 (it stops before $0.60).");
    expect(estimateSentence(null)).toBe("The cost estimate is unavailable.");
    expect(formatUsd(null)).toBe("unknown");
  });

  it("states the run in plain words", () => {
    const run = (over: any) => parseAiCheck(payload({ run: { ...payload().run, ...over } }))!.run;
    expect(runLine(null)).toBe("No AI check has been run for this company yet.");
    expect(runLine(run({}))).toMatch(/^24 answers · \d+ \w+ 2026 · cost \$0\.31\.$/);
    expect(runLine(run({ status: "stopped_at_cap" }))).toContain("Stopped early at the cost limit.");
    expect(runLine(run({ status: "running", calls_ok: 5 }))).toBe("Running… 5 of 24 answers so far.");
    expect(runLine(run({ status: "failed", calls_ok: 0, error: "no answers" }))).toBe("The last AI check failed: no answers");
  });

  it("stability tones", () => {
    expect(stabilityTone({ stable: true })).toBe("same");
    expect(stabilityTone({ stable: false })).toBe("varies");
    expect(stabilityTone({ stable: null })).toBe("unknown");
  });

  it("never says content can be removed, and calls the list internal and for legal review", () => {
    const all = `${REMOVAL_LIST_TITLE} ${REMOVAL_LIST_NOTICE}`;
    expect(all).toMatch(/internal/i);
    expect(all).toMatch(/legal/i);
    expect(REMOVAL_LIST_NOTICE).toContain("does not say any page can be removed");
    // the only mention of removal is the negation; no claim that content is, can be, should be or must be removed
    const withoutNegation = REMOVAL_LIST_NOTICE.replace("does not say any page can be removed", "");
    expect(withoutNegation).not.toMatch(/\b(is|are|can be|could be|should be|must be) (removed|taken down|deleted|taken offline)\b/i);
    expect(CARD_NOTICE).toContain("not a score");
  });
});
