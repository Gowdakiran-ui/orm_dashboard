// Renders the real Executives tab (jsdom) with the API mocked. The page must show nothing but the search box until a search is made.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  searchExecutive: vi.fn(),
  addExecutiveCandidate: vi.fn(),
  fetchReviewedExecutiveCandidates: vi.fn(),
  fetchDocumentDetails: vi.fn(),
}));
vi.mock("@/lib/api", () => api);
// recharts needs real layout; the chart is not under test here
vi.mock("recharts", () => {
  const Box = ({ children }: any) => React.createElement("div", { "data-chart": true }, children);
  return { ResponsiveContainer: Box, BarChart: Box, Bar: Box, XAxis: Box, YAxis: Box, CartesianGrid: Box, Tooltip: Box };
});

import { ExecutivesTab } from "./ExecutivesTab";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

let host: HTMLDivElement;
let root: Root;

async function mount(clientId = "client-1", trackedExecutives?: any[]) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root.render(React.createElement(ThemeProvider, null, React.createElement(ExecutivesTab, { clientId, clientName: "Godrej Properties", trackedExecutives })));
  });
}

async function search(text: string) {
  const input = host.querySelector("input") as HTMLInputElement;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => { setter.call(input, text); input.dispatchEvent(new Event("input", { bubbles: true })); });
  await act(async () => { (host.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
  await act(async () => { await Promise.resolve(); });
}

const click = async (el: Element | null | undefined) => { await act(async () => { (el as HTMLElement).click(); }); };
const buttonByText = (label: string) => Array.from(host.querySelectorAll("button")).find(b => b.textContent?.trim() === label);

beforeEach(() => {
  Object.values(api).forEach((f: any) => f.mockReset());
  api.fetchDocumentDetails.mockResolvedValue({ url: null });
});
afterEach(async () => { await act(async () => { root.unmount(); }); host.remove(); });

describe("Executives page before any search", () => {
  it("shows only the header card, the search box and the empty-state card", async () => {
    await mount();
    const text = host.textContent || "";
    expect(text).toContain("Search Executives");
    expect(host.querySelector("input")?.getAttribute("placeholder")).toBe("Search executive name...");
    expect(text).toContain("No executive selected yet.");
    expect(text).toContain("Search a name above to start tracking a real executive.");
    for (const banned of ["Tracked Executives", "Candidates Found", "were hidden", "Add This Executive", "NOT YET TRACKED", "Documents Behind This Score"]) {
      expect(text).not.toContain(banned);
    }
    expect(host.querySelectorAll("table").length).toBe(0);
    expect(api.searchExecutive).not.toHaveBeenCalled();
    expect(api.fetchReviewedExecutiveCandidates).not.toHaveBeenCalled();     // the reviewed-candidates endpoint is not used by the page
  });
});

describe("default view: top tracked executives", () => {
  const tracked = [
    { entity_id: "a", name: "Gaurav Pandey", score: 0, health_status: "INSUFFICIENT_EVIDENCE", document_count: 0 },
    { entity_id: "b", name: "Pirojsha Godrej", score: 60.2, grade: "C", health_status: "COMPLETE", document_count: 2 },
    { entity_id: "c", name: "Geetika Trehan", score: 60.2, grade: "C", health_status: "COMPLETE", document_count: 1 },
    ...Array.from({ length: 8 }, (_, i) => ({ entity_id: `x${i}`, name: `Extra Person ${i}`, score: 50 - i, grade: "D", health_status: "COMPLETE", document_count: 5 })),
  ];

  it("lists at most 8 tracked people, scored first, and says why an unscored person has no score", async () => {
    await mount("client-1", tracked);
    const text = host.textContent || "";
    expect(text).toContain("Tracked executives");
    const cards = Array.from(host.querySelectorAll("button")).filter(b => b.textContent?.includes("Person") || b.textContent?.includes("Godrej") || b.textContent?.includes("Trehan") || b.textContent?.includes("Pandey"));
    expect(cards.length).toBe(8);
    expect(text).toContain("Pirojsha Godrej");
    expect(text).not.toContain("Gaurav Pandey");           // 11 tracked, unscored sorts last and falls outside the top 8
    expect(text).not.toContain("No executive selected yet.");
  });

  it("an unscored person shows a plain reason, and a card opens the same read-only search", async () => {
    await mount("client-1", tracked.slice(0, 3));
    expect(host.textContent).toContain("No coverage mentioning Godrej Properties together with this person in the last 30 days.");
    api.searchExecutive.mockResolvedValue({ status: "tracked_no_coverage", executive: { name: "Gaurav Pandey", entity_id: "a" }, client_name: "Godrej Properties" });
    await click(buttonByText("Gaurav Pandey") ?? Array.from(host.querySelectorAll("button")).find(b => b.textContent?.includes("Gaurav Pandey")));
    await act(async () => { await Promise.resolve(); });
    expect(api.searchExecutive).toHaveBeenCalledWith("client-1", "Gaurav Pandey");
    expect(host.textContent).toContain("Older articles may exist; they are not counted.");
  });

  it("never lists candidates and has no free-text add", async () => {
    await mount("client-1", tracked.slice(0, 3));
    expect(host.textContent).not.toContain("Add This Executive");
    expect(api.fetchReviewedExecutiveCandidates).not.toHaveBeenCalled();
  });
});

describe("search results", () => {
  it("candidate card and Add button appear only after a search; Add asks for confirmation and adds exactly one person once", async () => {
    api.searchExecutive.mockResolvedValue({ status: "unpromoted_candidate", candidate: { id: "cand-9", name: "Anil Singhvi", mention_count: 2, confidence: 0.7 } });
    api.addExecutiveCandidate.mockResolvedValue({ status: "added", message: "Added. A score appears once new coverage mentions them." });
    await mount();
    expect(buttonByText("Add This Executive")).toBeUndefined();
    await search("Anil Singhvi");
    expect(api.searchExecutive).toHaveBeenCalledWith("client-1", "Anil Singhvi");
    expect(host.textContent).toContain("NOT YET TRACKED");
    await click(buttonByText("Add This Executive"));
    expect(host.textContent).toContain("Add Anil Singhvi?");
    expect(api.addExecutiveCandidate).not.toHaveBeenCalled();                  // nothing happens before the confirmation
    await click(buttonByText("Cancel"));
    expect(api.addExecutiveCandidate).not.toHaveBeenCalled();
    await click(buttonByText("Add This Executive"));
    api.searchExecutive.mockResolvedValue({ status: "tracked", executive: { name: "Anil Singhvi", entity_id: "e1", score: null, grade: null, health_status: "NO_SCORE_YET", events: [], sentiment_split: { positive: 0, neutral: 0, negative: 0 } } });
    await click(buttonByText("Confirm add"));
    expect(api.addExecutiveCandidate).toHaveBeenCalledTimes(1);
    expect(api.addExecutiveCandidate).toHaveBeenCalledWith("client-1", "cand-9");
    expect(host.textContent).toContain("Added. A score appears once new coverage mentions them.");
    expect(host.textContent).toContain("No score yet");
  });

  it("an ambiguous search shows only the message and no names", async () => {
    api.searchExecutive.mockResolvedValue({ status: "ambiguous", total: 2, names: [{ name: "Secret Person One", kind: "tracked" }, { name: "Secret Person Two", kind: "candidate" }] });
    await mount();
    await search("Secret");
    expect(host.textContent).toContain("Several people match that text. Type the full name.");
    expect(host.textContent).not.toContain("Secret Person");
    expect(host.querySelectorAll("button").length).toBe(1);      // the Search button only: no name buttons
  });

  it("not found, invalid name and tracked-without-coverage show their messages", async () => {
    await mount();
    api.searchExecutive.mockResolvedValue({ status: "not_found" });
    await search("Suraj Kumar");
    expect(host.textContent).toContain("No tracked executive or discovered candidate matches");
    expect(host.textContent).toContain("Only people already found in the coverage can be tracked");
    api.searchExecutive.mockResolvedValue({ status: "invalid_name", reason: "two names run together without a space" });
    await search("Nadir GodrejGautam Adani");
    expect(host.textContent).toContain("two names run together without a space");
    api.searchExecutive.mockResolvedValue({ status: "tracked_no_coverage", executive: { name: "Nadir Godrej", entity_id: "e2" }, client_name: "Godrej Properties" });
    await search("Nadir Godrej");
    expect(host.textContent).toContain("no article published in the last 30 days mentions Godrej Properties together with this person");
  });

  it("a tracked person shows the corrected display: events from the backend, Low evidence, withheld grade, Based on N documents, stale label", async () => {
    const events = [{ id: "d1", title: "Headline one", source: "Reuters", topic: "General", timestamp: "2026-10-01T00:00:00Z", sentiment: 0, risk: 0, reputation_impact: "+0.0", names_executive: true, snippet: "x" }];
    api.searchExecutive.mockResolvedValue({ status: "tracked", executive: {
      name: "Geetika Trehan", entity_id: "e3", score: 60.192, grade: "C", health_status: "PARTIAL", document_count: 1, events, sentiment_split: { positive: 0, neutral: 1, negative: 0 },
      as_of: "2026-09-01T00:00:00Z", biggest_drag: { label: "Sentiment", points_lost: 12.34 } } });
    await mount();
    await search("Geetika Trehan");
    const text = host.textContent || "";
    expect(text).toContain("60.19");
    expect(text).toContain("LOW EVIDENCE");
    expect(text).toContain("Grade withheld: fewer than 3 documents");
    expect(text).toContain("Based on 1 document. Biggest drag on the score: Sentiment (12.3 points lost).");
    expect(text).toContain("Stale: last scored");
    expect(text).toContain("1 document behind this score");
    expect(host.querySelectorAll("tbody tr").length).toBe(1);
    expect(text).toContain("Appears in Godrej Properties coverage");
  });
});
