// Renders the real Risk Center (jsdom): with the flagged-first list, a flagged article older than the newest 500 is a table row and shows its
// own date; without it, only the newest-500 list is read (the old behaviour, which showed none of Godrej's flagged articles).
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as any).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };      // jsdom has none; the table only uses it to show a scroll hint

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/api", () => ({ fetchDocumentDetails: vi.fn().mockResolvedValue({ url: null }) }));

import { RiskTab } from "./RiskTab";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

let host: HTMLDivElement | undefined;
let root: Root | undefined;

async function mount(props: any) {
  host = document.createElement("div");
  document.body.appendChild(host);
  const r = (root = createRoot(host));
  await act(async () => {
    r.render(React.createElement(ThemeProvider, null, React.createElement(RiskTab, {
      alertsLoading: false, alertsError: null, alerts: [], documentsLoading: false, documentsError: null, clientId: "c1", ...props,
    })));
  });
}
afterEach(async () => { if (root) { const r = root; await act(async () => { r.unmount(); }); } host?.remove(); root = undefined; host = undefined; });

const low = (i: number) => ({ id: `low${i}`, title: `Routine story ${i}`, source: "Reuters", document_type: "rss", timestamp: new Date(Date.UTC(2026, 10, 9 - i % 5, 6)).toISOString(), risk: 0, risk_exact: 0, risk_level: "LOW", scored: true, risk_explainability: {} });
const flagged = (id: string, title: string, risk: number, level: string, ts: string) => ({ id, title, source: "DNA India", document_type: "rss", timestamp: ts, risk: Math.round(risk), risk_exact: risk, risk_level: level, scored: true, risk_explainability: {} });
const newest = Array.from({ length: 40 }, (_, i) => low(i));
const old = [
  flagged("f1", "CBI FIR over environmental clearances", 51, "HIGH", "2026-03-04T10:30:00Z"),
  flagged("f2", "Godrej fined by MahaRERA", 51, "HIGH", "2025-06-01T08:00:00Z"),
  flagged("f3", "Hoarding penalty in Pune", 30, "MEDIUM", "2024-12-15T09:15:00Z"),
];

const rowTexts = () => Array.from(host!.querySelectorAll("tbody tr")).map(r => r.textContent || "");

describe("Risk Center list", () => {
  it("lists a flagged article older than the newest articles, with its own date", async () => {
    await mount({ documents: newest, flaggedDocuments: old });
    const rows = rowTexts();
    expect(rows).toHaveLength(3);
    const cbi = rows.find(r => r.includes("CBI FIR over environmental clearances"))!;
    expect(cbi).toContain("04-03-2026");
    expect(rows.find(r => r.includes("Godrej fined by MahaRERA"))).toContain("01-06-2025");
    expect(rows.find(r => r.includes("Hoarding penalty in Pune"))).toContain("15-12-2024");
    expect(rows.some(r => r.includes("Routine story"))).toBe(false);                  // LOW items are not risk events
  });

  it("without the flagged list only the newest articles are read: no flagged rows (the old behaviour)", async () => {
    await mount({ documents: newest });
    expect(rowTexts().filter(r => r.includes("CBI") || r.includes("MahaRERA"))).toHaveLength(0);
  });

  it("does not list an article twice when it is in both lists, strongest first", async () => {
    const recentFlag = flagged("n1", "Fresh probe notice", 62, "HIGH", "2026-11-08T07:00:00Z");
    await mount({ documents: [recentFlag, ...newest], flaggedDocuments: [recentFlag, ...old] });
    const rows = rowTexts();
    expect(rows).toHaveLength(4);
    expect(rows.filter(r => r.includes("Fresh probe notice"))).toHaveLength(1);
    expect(rows[0]).toContain("Fresh probe notice");                                   // 62 leads 51, 51, 30
    expect(rows[3]).toContain("Hoarding penalty in Pune");
  });
});
