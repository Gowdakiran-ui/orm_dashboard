import { describe, it, expect } from "vitest";
import { parsePipelineCost, formatCost, apifyLine, llmLine, searchLine, runLine, PIPELINE_COST_NOTE, type PipelineCostView } from "./pipelineCost";

const last = (over: any = {}) => ({
  run_id: "6c71f6e1-aaaa-bbbb-cccc-000000000000", finalized: true,
  run: { status: "SUCCESS", stage: "SUCCESS", started_at: "2026-11-09T10:00:00+00:00", finished_at: "2026-11-09T10:21:00+00:00", duration_s: 1260 },
  apify: { calls: 2, cost_usd: 0.1235, estimated: true, by_source: { reddit: { calls: 1, usd: 0.056, estimated: false }, instagram: { calls: 1, usd: 0.0675, estimated: true } } },
  llm: { calls: 59, tokens_prompt: 19749, tokens_completion: 2194, est_cost_usd: 0.0307, by_type: {
    risk_case_status: { calls: 40, failed: 0, tokens_prompt: 12000, tokens_completion: 1100, est_usd: 0.0175, price_known: true, model: "anthropic/claude-haiku-4.5" },
    brand_new_call: { calls: 2, failed: 0, tokens_prompt: 100, tokens_completion: 10, est_usd: 0, price_known: false, model: null } } },
  search: { calls: 3, by_source: { youtube: 2, reddit: 1 } },
  total_usd: 0.1542, ...over,
});

describe("parsePipelineCost", () => {
  it("reads a full payload", () => {
    const r = parsePipelineCost({ last_run: last() });
    expect(r.state).toBe("ready");
    const c = (r as any).cost as PipelineCostView;
    expect(c).toMatchObject({ finalized: true, totalUsd: 0.1542 });
    expect(c.apify.rows.map(x => [x.key, x.usd, x.estimated, x.note])).toEqual([["reddit", 0.056, false, "reported by Apify"], ["instagram", 0.0675, true, "estimated"]]);
    expect(c.llm.rows[0]).toMatchObject({ key: "risk_case_status", calls: 40, usd: 0.0175, note: "anthropic/claude-haiku-4.5" });
    expect(c.llm.rows[1]).toMatchObject({ key: "brand_new_call", usd: null, note: "no price listed, not costed" });
    expect(c.search.rows).toEqual([{ key: "youtube", calls: 2 }, { key: "reddit", calls: 1 }]);
    expect(c.run).toMatchObject({ status: "SUCCESS", durationS: 1260 });
  });

  it("no metered run is empty, and anything malformed is unavailable, never a zero", () => {
    expect(parsePipelineCost({ last_run: null })).toEqual({ state: "empty" });
    for (const bad of [null, undefined, {}, { last_run: {} }, { last_run: last({ apify: null }) }, { last_run: last({ total_usd: "1" }) }, { last_run: last({ run_id: "" }) }, "x"]) {
      expect(parsePipelineCost(bad)).toEqual({ state: "unavailable" });
    }
  });

  it("a run row without pipeline details still reads", () => {
    const c = (parsePipelineCost({ last_run: last({ run: null }) }) as any).cost as PipelineCostView;
    expect(c.run).toBeNull();
    expect(runLine(c)).toBe("Run 6c71f6e1.");
  });
});

describe("wording", () => {
  const c = (parsePipelineCost({ last_run: last() }) as any).cost as PipelineCostView;

  it("formats small dollar amounts with the precision they need", () => {
    expect(formatCost(0.0123)).toBe("$0.0123");
    expect(formatCost(1.2)).toBe("$1.20");
    expect(formatCost(0)).toBe("$0.0000");
    expect(formatCost(null)).toBe("unknown");
  });

  it("says which Apify figures are reported and which are estimated, and that the LLM figure is an estimate", () => {
    expect(apifyLine(c)).toBe("2 calls, $0.1235 (partly estimated)");
    expect(apifyLine({ ...c, apify: { ...c.apify, estimated: false } })).toBe("2 calls, $0.1235 (reported by Apify)");
    expect(apifyLine({ ...c, apify: { ...c.apify, calls: 0 } })).toBe("No Apify call in this run.");
    expect(llmLine(c)).toBe("59 calls, 19,749 tokens in, 2,194 out, about $0.0307 (estimated)");
    expect(llmLine({ ...c, llm: { ...c.llm, calls: 0 } })).toBe("No LLM call in this run.");
    expect(searchLine(c)).toBe("3 keyword searches (youtube 2, reddit 1)");
    expect(searchLine({ ...c, search: { calls: 0, rows: [] } })).toBe("No keyword search in this run.");
  });

  it("states the run and says when it is still counting", () => {
    expect(runLine(c)).toBe("Run 6c71f6e1 · success · 09-11-2026 · 1260 s.");
    expect(runLine({ ...c, finalized: false })).toContain("Still counting: the run has not finished.");
  });

  it("the note says super admins only, estimated figures and no effect on any score", () => {
    expect(PIPELINE_COST_NOTE).toMatch(/Super admins only/);
    expect(PIPELINE_COST_NOTE).toMatch(/estimate/);
    expect(PIPELINE_COST_NOTE).toMatch(/changes no score/);
  });
});
