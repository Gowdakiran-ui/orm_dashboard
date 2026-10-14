// Export Report button: idle/disabled/preparing/error states, the click-time data snapshot, and the download.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const render = vi.hoisted(() => ({ fn: vi.fn() }));
vi.mock("@/lib/exportReport", () => ({ renderReportPdf: render.fn }));
// The real stage needs a laid-out browser; here it just reports that the capture finished (or failed).
const stage = vi.hoisted(() => ({ mode: "ok" as "ok" | "fail", seenInputs: [] as any[] }));
vi.mock("@/components/ExportReportStage", async () => {
  const R = await import("react");
  return {
    ExportReportStage: ({ input, onDone, onError }: any) => {
      stage.seenInputs.push(input);
      R.useEffect(() => {
        Promise.resolve().then(() => (stage.mode === "ok" ? onDone({}) : onError(new Error("Sentiment Breakdown chart was captured blank."))));
      }, []);
      return null;
    },
  };
});

import { ExportReportButton } from "./ExportReportButton";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import type { ReportInput } from "@/utils/reportModel";

let host: HTMLDivElement;
let root: Root;
const base = (over: any = {}): ReportInput => ({
  clientId: "c1", clientName: "Client One", generatedAt: new Date("2026-10-01T20:00:00Z"), userEmail: "me@example.com", browserTimeZone: "Asia/Calcutta",
  reputationSummary: null, reputationSummaryError: "x", planAdvisory: null, planAdvisoryError: "x", executives: [], executivesError: null,
  benchmarks: [], benchmarksError: null, documents: [], documentsError: null, alerts: [], alertsError: null, repHistory: [], historyError: null,
  analytics: { sentimentDistData: [], topicDistData: [], riskMatrixData: [], riskHeatmapData: { categories: [], severities: [], grid: {} }, alertTimelineData: [] },
  ...over,
});
async function mount(props: any) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => { root.render(React.createElement(ThemeProvider, { children: React.createElement(ExportReportButton, props) })); });
}
const btn = () => host.querySelector("button") as HTMLButtonElement;
const flush = async () => { for (let i = 0; i < 6; i++) await act(async () => { await Promise.resolve(); }); };

let downloads: { name: string; href: string }[] = [];
beforeEach(() => {
  render.fn.mockReset();
  render.fn.mockResolvedValue(new Blob(["%PDF-fake"]));
  stage.mode = "ok";
  stage.seenInputs = [];
  downloads = [];
  (URL as any).createObjectURL = vi.fn(() => "blob:fake");
  (URL as any).revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { downloads.push({ name: this.download, href: this.href }); });
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(async () => { await act(async () => { root.unmount(); }); host.remove(); vi.restoreAllMocks(); });

describe("Export Report button", () => {
  it("is idle: Export Report, enabled, and reads no data until clicked", async () => {
    const getSnapshot = vi.fn(() => base());
    await mount({ getSnapshot, disabled: false });
    expect(btn().textContent).toContain("Export Report");
    expect(btn().disabled).toBe(false);
    expect(getSnapshot).not.toHaveBeenCalled();
  });
  it("is disabled, with the reason as its title, while data loads or no client is selected, and does nothing on click", async () => {
    const getSnapshot = vi.fn(() => base());
    await mount({ getSnapshot, disabled: true, disabledReason: "Select a company first" });
    expect(btn().disabled).toBe(true);
    expect(btn().title).toBe("Select a company first");
    await act(async () => { btn().click(); });
    expect(getSnapshot).not.toHaveBeenCalled();
  });
  it("shows Preparing report... while working, then downloads XOOP_<Client>_Reputation_Report_<IST date>.pdf", async () => {
    let finish: (b: Blob) => void = () => {};
    render.fn.mockImplementation(() => new Promise<Blob>(r => { finish = r; }));
    await mount({ getSnapshot: () => base(), disabled: false });
    await act(async () => { btn().click(); });
    await flush();
    expect(btn().textContent).toContain("Preparing report...");
    expect(btn().disabled).toBe(true);
    await act(async () => { finish(new Blob(["%PDF"])); });
    await flush();
    expect(btn().textContent).toContain("Export Report");
    expect(downloads).toEqual([{ name: "XOOP_Client_One_Reputation_Report_2026-10-02.pdf", href: "blob:fake" }]);
  });
  it("freezes the data at click time: a client switch or re-poll afterwards cannot change the report", async () => {
    let current = base({ clientName: "Client One", clientId: "c1" });
    const getSnapshot = vi.fn(() => current);
    let release: () => void = () => {};
    render.fn.mockImplementation(async (model: any) => {
      await new Promise<void>(r => { release = r; });
      return new Blob([model.meta.clientName]);
    });
    await mount({ getSnapshot, disabled: false });
    await act(async () => { btn().click(); });
    await flush();
    // the user switches client and the dashboard re-polls while the report is being made
    current = base({ clientName: "Client Two", clientId: "c2" });
    current.documents = [{ id: "x" }] as any;
    await act(async () => { release(); });
    await flush();
    expect(getSnapshot).toHaveBeenCalledTimes(1);
    expect(render.fn.mock.calls[0][0].meta.clientName).toBe("Client One");
    expect(stage.seenInputs[0].clientId).toBe("c1");
    expect(downloads[0].name).toContain("Client_One");
  });
  it("shows a clear inline error when the capture fails, and can be retried", async () => {
    stage.mode = "fail";
    await mount({ getSnapshot: () => base(), disabled: false });
    await act(async () => { btn().click(); });
    await flush();
    expect(host.querySelector("[role=alert]")?.textContent).toContain("Export failed: Sentiment Breakdown chart was captured blank.");
    expect(render.fn).not.toHaveBeenCalled();
    expect(downloads).toHaveLength(0);
    expect(btn().disabled).toBe(false);
    stage.mode = "ok";
    await act(async () => { btn().click(); });
    await flush();
    expect(host.querySelector("[role=alert]")).toBeNull();
    expect(downloads).toHaveLength(1);
  });
  it("shows an error when PDF rendering throws", async () => {
    render.fn.mockRejectedValue(new Error("font missing"));
    await mount({ getSnapshot: () => base(), disabled: false });
    await act(async () => { btn().click(); });
    await flush();
    expect(host.querySelector("[role=alert]")?.textContent).toContain("font missing");
    expect(downloads).toHaveLength(0);
  });
});
