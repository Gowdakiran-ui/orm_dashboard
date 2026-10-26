// Renders the real Intelligence Stream tab (jsdom) with the details API mocked: row fields, drawer fields, row dates, and paging reset on client change.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({ fetchDocumentDetails: vi.fn() }));
vi.mock("@/lib/api", () => api);

import { formatDMYTime } from "@/utils/dateFormat";
import { FeedTab } from "./FeedTab";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

let host: HTMLDivElement;
let root: Root;

const doc = (i: number, over: any = {}) => ({
  id: `d${i}`, title: `Headline ${i}`, source: "Adani Group RSS Source", document_type: "rss",
  timestamp: new Date(Date.now() - i * 60000).toISOString(), sentiment: 0, risk: 0, topic: "General", ...over,
});
const manyDocs = (n: number) => Array.from({ length: n }, (_, i) => doc(i));

async function mount(props: any) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await render(props);
}
async function render(props: any) {
  await act(async () => {
    root.render(React.createElement(ThemeProvider, null, React.createElement(FeedTab, {
      documentsLoading: false, documentsError: null, documents: [], clientId: "client-1", ...props,
    })));
  });
}
const click = async (el: Element | null | undefined) => { await act(async () => { (el as HTMLElement).click(); }); };
const rowEls = () => Array.from(host.querySelectorAll(".space-y-2\\.5 > div"));
const buttonByText = (label: RegExp) => Array.from(host.querySelectorAll("button")).find(b => label.test(b.textContent?.trim() || ""));
const rowTime = (i: number) => rowEls()[i].children[0].children[1].textContent?.trim();
async function openDetails(i: number) {
  await click(rowEls()[i].querySelector("button"));
  await act(async () => { await Promise.resolve(); });
}
const drawerText = () => document.body.querySelector(".fixed.inset-0.z-50")?.textContent || "";

beforeEach(() => { api.fetchDocumentDetails.mockReset(); });
afterEach(async () => { await act(async () => { root.unmount(); }); host.remove(); });

describe("row fields (unchanged by the fixes)", () => {
  it("shows title, source, topic, risk and sentiment exactly as given", async () => {
    await mount({ documents: [doc(0, { title: "Risky one", risk: 33, sentiment: -1, topic: "Legal Risk" })] });
    const text = rowEls()[0].textContent || "";
    expect(text).toContain("Risky one");
    expect(text).toContain("Adani Group RSS Source");
    expect(text).toContain("Legal Risk");
    expect(text).toContain("Risk: 33");
    expect(text).toContain("-1.00");
  });
});

describe("B9 empty state", () => {
  it("reads 'No intelligence documents match in database.' when there are no documents", async () => {
    await mount({ documents: [] });
    expect(host.textContent).toContain("No intelligence documents match in database.");
    expect(host.textContent).not.toContain("matches in database");
  });
});

describe("B1 drawer date", () => {
  it("shows the list row's real date instead of 'Recent' (detail payload has no timestamp)", async () => {
    api.fetchDocumentDetails.mockResolvedValue({ title: "Old story", source_id: "S", topics: [], entities: [], sentiment: 0, risk: 0, url: null });
    await mount({ documents: [doc(0, { id: "old", title: "Old story", timestamp: "2017-08-16T11:48:47+00:00" })] });
    await openDetails(0);
    const text = drawerText();
    expect(text).toContain(new Date("2017-08-16T11:48:47+00:00").toLocaleString());
    expect(text).not.toContain("Published Recent");
  });
  it("still falls back to 'Recent' when neither the detail nor the list row has a date", async () => {
    api.fetchDocumentDetails.mockResolvedValue({ title: "No date", topics: [], entities: [], sentiment: 0, risk: 0, url: null });
    await mount({ documents: [doc(0, { timestamp: null })] });
    await openDetails(0);
    expect(drawerText()).toContain("Published Recent");
  });
});

describe("B2 classification strength", () => {
  it("null confidence shows N/A, not 0%", async () => {
    api.fetchDocumentDetails.mockResolvedValue({ title: "T", topics: [{ name: "General", confidence: null }], entities: [], sentiment: 0, risk: 0, url: null });
    await mount({ documents: [doc(0)] });
    await openDetails(0);
    const text = drawerText();
    expect(text).toContain("Classification StrengthN/A");
    expect(text).not.toContain("Classification Strength0%");
  });
  it("a real confidence is unchanged", async () => {
    api.fetchDocumentDetails.mockResolvedValue({ title: "T", topics: [{ name: "Innovation", confidence: 0.69 }], entities: [], sentiment: 0, risk: 0, url: null });
    await mount({ documents: [doc(0)] });
    await openDetails(0);
    expect(drawerText()).toContain("Classification Strength69%");
  });
});

describe("B4 row dates", () => {
  it("every row shows its date as DD-MM-YYYY, today's included, then the time", async () => {
    const today = new Date();
    const old = new Date("2017-08-16T11:48:47+00:00");
    await mount({ documents: [doc(0, { timestamp: today.toISOString() }), doc(1, { timestamp: old.toISOString() })] });
    expect(rowTime(0)).toBe(formatDMYTime(today));
    expect(rowTime(0)).toMatch(/^\d{2}-\d{2}-\d{4}, \d{2}:\d{2} (AM|PM)$/);
    expect(rowTime(1)).toBe(formatDMYTime(old));
    expect(rowTime(1)).toContain("-2017");
  });
  it("a row with no timestamp still reads 'Recent'", async () => {
    await mount({ documents: [doc(0, { timestamp: null })] });
    expect(rowTime(0)).toBe("Recent");
  });
});

describe("B6 paging resets on client change", () => {
  it("Load more to the end, switch client: back to 50 rows; switch back: 50 again", async () => {
    await mount({ documents: manyDocs(120), clientId: "godrej" });
    expect(rowEls().length).toBe(50);
    await click(buttonByText(/^Load \d+ more/i));
    await click(buttonByText(/^Load \d+ more/i));
    expect(rowEls().length).toBe(120);
    await render({ documents: manyDocs(120), clientId: "adani" });
    expect(rowEls().length).toBe(50);
    await render({ documents: manyDocs(120), clientId: "godrej" });
    expect(rowEls().length).toBe(50);
  });
});

const detail = (over: any = {}) => ({ title: "T", source_id: "S", topics: [{ name: "General", confidence: 0.5 }], entities: [], sentiment: 0, risk: 0, scored: true, url: null, normalized_content: "Headline 0", ...over });

describe("A1 drawer date label", () => {
  it("says Published (the value is the published date), not Ingested at", async () => {
    api.fetchDocumentDetails.mockResolvedValue(detail());
    await mount({ documents: [doc(0, { id: "p", timestamp: "2017-08-16T11:48:47+00:00" })] });
    await openDetails(0);
    const text = drawerText();
    expect(text).toContain("Published " + new Date("2017-08-16T11:48:47+00:00").toLocaleString());
    expect(text).not.toContain("Ingested at");
  });
});

describe("A2 AI summary section in the drawer", () => {
  const WHAT = "A 7% share price drop reported by Livemint.";
  const HOW = "Draft a brief note for the investor relations team.";
  it("shows the real what / how_to_solve text when ai_summary exists", async () => {
    api.fetchDocumentDetails.mockResolvedValue(detail({ risk: 33, risk_explainability: { ai_summary: { what: WHAT, how_to_solve: HOW, source: "generated" } } }));
    await mount({ documents: [doc(0, { risk: 33 })] });
    await openDetails(0);
    const text = drawerText();
    expect(text).toContain(WHAT);
    expect(text).toContain(HOW);
  });
  it("hides the whole section for a risk-0 row (explainability without ai_summary): no title repeat, no invented text", async () => {
    api.fetchDocumentDetails.mockResolvedValue(detail({ title: "Plain row", normalized_content: "Plain row", risk_explainability: { final_score: 0, confidence: 0.4 } }));
    await mount({ documents: [doc(0, { title: "Plain row" })] });
    await openDetails(0);
    const text = drawerText();
    expect(text).not.toContain("AI Classification Summary");
    expect(text).not.toContain("Initial pipeline trace");
    expect(text.split("Plain row").length - 1).toBe(1); // the title appears once (the heading), not repeated as a summary
  });
  it("hides the section for an unscored row (no risk_explainability at all) and when ai_summary is empty", async () => {
    api.fetchDocumentDetails.mockResolvedValue(detail({ scored: false, risk_explainability: {} }));
    await mount({ documents: [doc(0, { scored: false })] });
    await openDetails(0);
    expect(drawerText()).not.toContain("AI Classification Summary");
    api.fetchDocumentDetails.mockResolvedValue(detail({ risk_explainability: { ai_summary: { what: "", how_to_solve: null } } }));
    await click(document.body.querySelector(".fixed.inset-0.z-50 button") as any);
    await openDetails(0);
    expect(drawerText()).not.toContain("AI Classification Summary");
  });
});

describe("A3 Not scored", () => {
  it("an unscored row shows one Not scored pill instead of Risk and sentiment pills; a scored risk-0 row is unchanged", async () => {
    await mount({ documents: [doc(0, { id: "u", scored: false, sentiment: -1 }), doc(1, { id: "s", scored: true, risk: 0, sentiment: 0 })] });
    const un = rowEls()[0].textContent || "";
    expect(un).toContain("Not scored");
    expect(un).not.toContain("Risk:");
    expect(un).not.toContain("-1.00");
    const sc = rowEls()[1].textContent || "";
    expect(sc).toContain("Risk: 0");
    expect(sc).toContain("0.00");
    expect(sc).not.toContain("Not scored");
  });
  it("a row without a scored field (older payload) is treated as scored", async () => {
    await mount({ documents: [doc(0)] });
    expect(rowEls()[0].textContent).toContain("Risk: 0");
  });
  it("the drawer shows Not scored in the Sentiment and Risk fields for an unscored row", async () => {
    api.fetchDocumentDetails.mockResolvedValue(detail({ scored: false, sentiment: -1, risk: 0 }));
    await mount({ documents: [doc(0, { scored: false })] });
    await openDetails(0);
    const text = drawerText();
    expect(text).toContain("Sentiment ScoreNot scored");
    expect(text).toContain("Risk IndexNot scored");
  });
  it("the drawer for a scored row is unchanged", async () => {
    api.fetchDocumentDetails.mockResolvedValue(detail({ scored: true, sentiment: -1, risk: 33 }));
    await mount({ documents: [doc(0, { risk: 33 })] });
    await openDetails(0);
    const text = drawerText();
    expect(text).toContain("Sentiment Score-1.00");
    expect(text).toContain("Risk Index33 pts");
  });
});

describe("A4 truncation notice", () => {
  it("shows the notice when the list is exactly the 500 cap; not for 449 or 499", async () => {
    await mount({ documents: manyDocs(500) });
    expect(host.textContent).toContain("Showing newest 500");
    await render({ documents: manyDocs(449) });
    expect(host.textContent).not.toContain("Showing newest");
    await render({ documents: manyDocs(499) });
    expect(host.textContent).not.toContain("Showing newest");
  });
});

describe("A5 subtitle size and drawer text selection", () => {
  it("the subtitle is 12px", async () => {
    await mount({ documents: [doc(0)] });
    const sub = Array.from(host.querySelectorAll("*")).find(e => e.children.length === 0 && e.textContent === "Real-time matching documents");
    expect(sub?.className).toContain("text-[12px]");
    expect(sub?.className).not.toContain("text-[9px]");
  });
  it("the drawer is selectable; the row list stays select-none", async () => {
    api.fetchDocumentDetails.mockResolvedValue(detail());
    await mount({ documents: [doc(0)] });
    expect(rowEls()[0].closest(".select-none")).not.toBeNull();
    expect(rowEls()[0].closest(".select-text")).toBeNull();
    await openDetails(0);
    const drawer = document.body.querySelector(".fixed.inset-0.z-50") as HTMLElement;
    expect(drawer.className).toContain("select-text");
  });
});

describe("A6 Mentioned Targets de-duplication", () => {
  it("lists each target once even if the payload repeats it", async () => {
    api.fetchDocumentDetails.mockResolvedValue(detail({ entities: [{ name: "Gautam Adani" }, { name: "Gautam Adani" }, { name: "Pranav Adani" }, { name: "Gautam Adani" }] }));
    await mount({ documents: [doc(0)] });
    await openDetails(0);
    const badges = Array.from(document.body.querySelectorAll(".fixed.inset-0.z-50 span")).filter(e => e.children.length === 0).map(e => e.textContent);
    expect(badges.filter(t => t === "Gautam Adani").length).toBe(1);
    expect(badges.filter(t => t === "Pranav Adani").length).toBe(1);
  });
});
