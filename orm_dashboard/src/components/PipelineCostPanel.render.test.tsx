// Renders the real Run Pipeline cost panel (jsdom) against a mocked API.
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({ fetchPipelineCost: vi.fn() }));
vi.mock("@/lib/api", () => api);

import { PipelineCostPanel } from "./PipelineCostPanel";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

let host: HTMLDivElement;
let root: Root;

async function mount(clientId: string | null = "c1") {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root.render(React.createElement(ThemeProvider, null, React.createElement(PipelineCostPanel, { clientId })));
  });
  await act(async () => { await Promise.resolve(); });
}
afterEach(async () => { await act(async () => { root.unmount(); }); host.remove(); });
beforeEach(() => { api.fetchPipelineCost.mockReset(); });

const payload = {
  last_run: {
    run_id: "6c71f6e1-aaaa", finalized: true,
    run: { status: "SUCCESS", stage: "SUCCESS", started_at: "2026-11-09T10:00:00+00:00", finished_at: "2026-11-09T10:21:00+00:00", duration_s: 1260 },
    apify: { calls: 1, cost_usd: 0.056, estimated: false, by_source: { reddit: { calls: 1, usd: 0.056, estimated: false } } },
    llm: { calls: 20, tokens_prompt: 6683, tokens_completion: 720, est_cost_usd: 0.0103, by_type: { risk_case_status: { calls: 20, failed: 0, tokens_prompt: 6683, tokens_completion: 720, est_usd: 0.0103, price_known: true, model: "anthropic/claude-haiku-4.5" } } },
    search: { calls: 2, by_source: { youtube: 2 } }, total_usd: 0.0663,
  },
};

describe("PipelineCostPanel", () => {
  it("shows the last run's total and the Apify, LLM and search lines", async () => {
    api.fetchPipelineCost.mockResolvedValue(payload);
    await mount();
    expect(host.querySelector("[data-testid='cost-total']")!.textContent).toBe("$0.0663");
    expect(host.textContent).toContain("1 call, $0.0560 (reported by Apify)");
    expect(host.textContent).toContain("20 calls, 6,683 tokens in, 720 out, about $0.0103 (estimated)");
    expect(host.textContent).toContain("2 keyword searches (youtube 2)");
    expect(host.querySelectorAll("[data-testid='cost-row']").length).toBe(2);
    expect(host.textContent).toContain("Super admins only");
    expect(api.fetchPipelineCost).toHaveBeenCalledWith("c1", expect.anything());
  });

  it("says so when no run has been metered, and when the cost cannot be read (never a zero)", async () => {
    api.fetchPipelineCost.mockResolvedValue({ last_run: null });
    await mount();
    expect(host.textContent).toContain("No pipeline run has been metered for this company yet.");
    expect(host.querySelector("[data-testid='cost-total']")).toBeNull();
    await act(async () => { root.unmount(); }); host.remove();
    api.fetchPipelineCost.mockRejectedValue(new Error("HTTP 403"));
    await mount();
    expect(host.textContent).toContain("The cost is unavailable right now.");
    expect(host.querySelector("[data-testid='cost-total']")).toBeNull();
  });

  it("makes no request without a company", async () => {
    await mount(null);
    expect(api.fetchPipelineCost).not.toHaveBeenCalled();
  });
});
