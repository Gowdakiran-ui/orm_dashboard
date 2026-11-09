// Renders the real "What AI says about you" card (jsdom) against a mocked API: hidden when the feature is off, per-question
// answers with source reliability and a stability marker, the low-reliability list for everyone, and the internal removal list
// only when the server sent it (super admin).
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({ fetchAiCheck: vi.fn(), runAiCheck: vi.fn() }));
vi.mock("@/lib/api", () => api);

import { AiCheckCard } from "./AiCheckCard";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

let host: HTMLDivElement;
let root: Root;

async function mount(clientId: string | null = "c1") {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root.render(React.createElement(ThemeProvider, null, React.createElement(AiCheckCard, { clientId })));
  });
  await act(async () => { await Promise.resolve(); });
}
afterEach(async () => { await act(async () => { root.unmount(); }); host.remove(); vi.clearAllMocks(); });
beforeEach(() => { api.fetchAiCheck.mockReset(); api.runAiCheck.mockReset(); });

const page = { url: "https://www.inventiva.co.in/story", title: "Godrej and the shadow of an FIR", domain: "inventiva.co.in", tier: "low", reliability: "Low", questions: ["Legal cases and controversies"], cited_in_answers: 3 };
const prompt = (over: any = {}) => ({
  key: "legal_controversies", label: "Legal cases and controversies", question: "What legal cases involve Godrej?", runs: 3,
  short_answer: "A CBI FIR over environmental clearances is being challenged in court.",
  sources: [{ domain: "hindustantimes.com", tier: "medium", reliability: "Medium", low_reliability: false, cited_in_runs: 3 }, { domain: "inventiva.co.in", tier: "low", reliability: "Low", low_reliability: true, cited_in_runs: 3 }],
  stable: false, stability: "Cited pages changed between the 3 runs (50% of pages shared).", ...over,
});
const payload = (over: any = {}) => ({
  enabled: true, can_run: false,
  run: { id: "r1", status: "completed", started_at: "2026-11-07T10:00:00+00:00", finished_at: "2026-11-07T10:03:00+00:00", cost_usd: 0.31, estimated_cost_usd: 0.324, calls_ok: 24, calls_failed: 0, repeats: 3, prompt_count: 8, model: "anthropic/claude-haiku-4.5", error: null },
  prompts: [prompt(), prompt({ key: "trustworthy", label: "Is it trustworthy?", stable: true, stability: "Same pages cited in all 3 runs." })],
  low_reliability_pages: [page], removal_candidates: [],
  estimate: { calls: 24, prompts: 8, repeats: 3, estimated_cost_usd: 0.324, cap_usd: 0.6 }, ...over,
});

describe("AI check card", () => {
  it("renders nothing while the feature is switched off, while loading, and when the request fails", async () => {
    api.fetchAiCheck.mockResolvedValue({ enabled: false });
    await mount();
    expect(host.querySelector("[data-testid='ai-check-card']")).toBeNull();
    await act(async () => { root.unmount(); }); host.remove();
    api.fetchAiCheck.mockRejectedValue(new Error("HTTP 500"));
    await mount();
    expect(host.textContent).toBe("");
  });

  it("shows, per question, the short answer, cited domains with their reliability, and a stability marker", async () => {
    api.fetchAiCheck.mockResolvedValue(payload());
    await mount();
    const rows = host.querySelectorAll("[data-testid='ai-check-prompt']");
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("A CBI FIR over environmental clearances");
    expect(rows[0].textContent).toContain("hindustantimes.com");
    expect(Array.from(rows[0].querySelectorAll("[data-testid='reliability-chip']")).map(e => e.textContent)).toEqual(["Medium", "Low"]);
    expect(rows[0].querySelector("[data-testid='stability-marker']")!.getAttribute("data-tone")).toBe("varies");
    expect(rows[1].querySelector("[data-testid='stability-marker']")!.getAttribute("data-tone")).toBe("same");
    expect(host.textContent).toContain("changes no score, risk or alert");
    expect(host.textContent).toContain("24 answers");
  });

  it("lists the cited pages from low-reliability outlets for any viewer, and shows no removal list or run button to a non-admin", async () => {
    api.fetchAiCheck.mockResolvedValue(payload());
    await mount();
    const low = host.querySelector("[data-testid='ai-check-low-pages']")!;
    expect(low.textContent).toContain("Cited pages from low-reliability outlets (1)");
    expect(low.textContent).toContain("Godrej and the shadow of an FIR");
    expect((low.querySelector("a") as HTMLAnchorElement).rel).toContain("noopener");
    expect(host.querySelector("[data-testid='removal-candidates']")).toBeNull();
    expect(host.textContent).not.toContain("Run AI check");
  });

  it("shows the internal removal list, clearly labelled and without claiming anything can be removed, to a super admin", async () => {
    api.fetchAiCheck.mockResolvedValue(payload({ can_run: true, removal_candidates: [page] }));
    await mount();
    const box = host.querySelector("[data-testid='removal-candidates']")!;
    expect(box.textContent).toContain("Possible removal candidates");
    expect(box.textContent).toContain("Internal");
    expect(box.textContent).toContain("Needs legal review");
    expect(box.textContent).toContain("does not say any page can be removed");
    expect(host.textContent).toContain("Run AI check");
  });

  it("run button first shows the printed estimate, asks nothing until confirmed, and then starts the paid run", async () => {
    api.fetchAiCheck.mockResolvedValue(payload({ can_run: true }));
    api.runAiCheck.mockImplementation(async (_id: string, dry: boolean) => (dry ? { dry_run: true, estimate: payload().estimate, questions: [] } : { dry_run: false, run_id: "r2", status: "running" }));
    await mount();
    const btn = Array.from(host.querySelectorAll("button")).find(b => b.textContent === "Run AI check")!;
    await act(async () => { btn.click(); });
    expect(api.runAiCheck).toHaveBeenCalledTimes(1);
    expect(api.runAiCheck).toHaveBeenLastCalledWith("c1", true);                       // dry run only: nothing is asked yet
    const box = host.querySelector("[data-testid='ai-check-confirm']")!;
    expect(box.textContent).toContain("8 questions asked 3 times = 24 paid web searches, about $0.32");
    const yes = Array.from(box.querySelectorAll("button")).find(b => b.textContent === "Yes, run it")!;
    await act(async () => { yes.click(); });
    expect(api.runAiCheck).toHaveBeenLastCalledWith("c1", false);
    expect(host.querySelector("[data-testid='ai-check-confirm']")).toBeNull();
  });

  it("cancel leaves nothing started, and a server refusal is shown", async () => {
    api.fetchAiCheck.mockResolvedValue(payload({ can_run: true }));
    api.runAiCheck.mockRejectedValue(new Error("An AI check for this client is still running."));
    await mount();
    const btn = Array.from(host.querySelectorAll("button")).find(b => b.textContent === "Run AI check")!;
    await act(async () => { btn.click(); });
    expect(host.querySelector("[role='alert']")!.textContent).toContain("still running");
    expect(api.runAiCheck).toHaveBeenCalledTimes(1);
  });

  it("empty state before the first run", async () => {
    api.fetchAiCheck.mockResolvedValue({ enabled: true, can_run: true, run: null, prompts: [], low_reliability_pages: [], removal_candidates: [], estimate: payload().estimate });
    await mount();
    expect(host.textContent).toContain("No AI check has been run for this company yet.");
    expect(host.querySelector("[data-testid='ai-check-low-pages']")).toBeNull();
  });
});
