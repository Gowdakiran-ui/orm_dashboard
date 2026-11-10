// Landing-page comparison chart: what the rendered table says and what backs it. Competitor cells are Yes, Partial or Unknown (never No);
// every Yes or Partial competitor cell has a source for that vendor; no source points outside the vendors' own sites; banned wording is absent.
import { describe, it, expect, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

import { ComparisonChartBody, chartRows, visibleChartRows, CHART_COLUMNS, CHART_FOOTNOTE, cellsOf } from "./ComparisonChart";

let host: HTMLDivElement | undefined;
let root: Root | undefined;
async function mount(showOptional = true) {
  host = document.createElement("div");
  document.body.appendChild(host);
  const r = (root = createRoot(host));
  await act(async () => { r.render(React.createElement(ComparisonChartBody, { showOptional })); });
}
afterEach(async () => { if (root) { const r = root; await act(async () => { r.unmount(); }); } host?.remove(); root = undefined; host = undefined; });

const VENDORS = ["Meltwater", "Brandwatch", "Sprinklr", "Talkwalker"];
const VENDOR_HOSTS: Record<string, RegExp> = {
  Meltwater: /(^|\.)meltwater\.com$/, Brandwatch: /(^|\.)brandwatch\.com$/, Sprinklr: /(^|\.)sprinklr\.com$/, Talkwalker: /(^|\.)(talkwalker|hootsuite)\.com$/,
};

describe("data", () => {
  it("has the eleven rows in order, columns XOOP | Meltwater | Brandwatch | Sprinklr | Talkwalker", () => {
    expect([...CHART_COLUMNS]).toEqual(["XOOP", "Meltwater", "Brandwatch", "Sprinklr", "Talkwalker"]);
    expect(chartRows.map(r => r.capability)).toEqual([
      "Sentiment scoring", "Risk scoring with the reason shown", "Legal status on risk items (allegation, probe, charged, settled, dismissed)",
      "One incident per story", "Executive tracking with sources", "Competitor benchmarking", "Alerting", "AI-answer visibility", "Hindi sentiment",
      "Automatic ongoing monitoring", "Content removal"]);
    expect(visibleChartRows(false).map(r => r.capability)).not.toContain("Hindi sentiment");
    expect(visibleChartRows(false)).toHaveLength(9);
  });

  it("never says No (or Planned or free text) for a competitor", () => {
    for (const r of chartRows) for (const cell of cellsOf(r).slice(1)) expect(["yes", "partial", "unknown"]).toContain(cell.level);
  });

  it("XOOP's own cells are as stated", () => {
    const x = Object.fromEntries(chartRows.map(r => [r.capability, r.xoop]));
    expect(x["Sentiment scoring"]).toEqual({ level: "yes", note: "English-language coverage" });
    expect(x["Legal status on risk items (allegation, probe, charged, settled, dismissed)"]).toEqual({ level: "yes", note: "from headlines" });
    expect(x["Competitor benchmarking"]).toEqual({ level: "partial", note: "tracked competitors, 90 days" });
    expect(x["Alerting"]).toEqual({ level: "partial", note: "in-app, after each refresh; no email yet" });
    expect(x["AI-answer visibility"]).toEqual({ level: "partial", note: "analyst-run snapshot on request; no client self-serve" });
    expect(x["Hindi sentiment"]).toEqual({ level: "no" });
    expect(x["Automatic ongoing monitoring"]).toEqual({ level: "no", note: "refresh on demand" });
    expect(x["Content removal"]).toEqual({ level: "text", note: "Offered separately by Onlyne's removal service" });
  });

  it("every Yes or Partial competitor cell has a source from that vendor's own site; other cells claim nothing", () => {
    for (const r of chartRows) {
      cellsOf(r).slice(1).forEach((cell, i) => {
        const vendor = VENDORS[i];
        const mine = r.sources.filter(s => s.vendor === vendor);
        if (cell.level === "unknown") expect(mine, `${r.capability} / ${vendor}`).toHaveLength(0);
        else expect(mine.length, `${r.capability} / ${vendor}`).toBeGreaterThan(0);
      });
      for (const s of r.sources) {
        const u = new URL(s.url);
        expect(u.protocol).toBe("https:");
        expect(u.hostname, s.url).toMatch(VENDOR_HOSTS[s.vendor]);
      }
    }
  });

  it("Meltwater's executive tracking is Partial with the manual-setup note, and only Hindi sentiment names Sprinklr as Yes", () => {
    const exec = chartRows.find(r => r.capability === "Executive tracking with sources")!;
    expect(exec.meltwater).toEqual({ level: "partial", note: "manual named-entity setup" });
    expect([exec.brandwatch, exec.sprinklr, exec.talkwalker].map(c => c.level)).toEqual(["unknown", "unknown", "unknown"]);
    const hindi = chartRows.find(r => r.capability === "Hindi sentiment")!;
    expect(hindi.sprinklr).toEqual({ level: "yes", note: "Hindi" });
    expect([hindi.meltwater, hindi.brandwatch, hindi.talkwalker].map(c => c.level)).toEqual(["unknown", "unknown", "unknown"]);
  });

  it("alerting: Meltwater and Talkwalker Yes, Brandwatch and Sprinklr Partial; AI-answer visibility: Meltwater Yes (add-on) only", () => {
    const a = chartRows.find(r => r.capability === "Alerting")!;
    expect([a.meltwater.level, a.brandwatch.level, a.sprinklr.level, a.talkwalker.level]).toEqual(["yes", "partial", "partial", "yes"]);
    const g = chartRows.find(r => r.capability === "AI-answer visibility")!;
    expect(g.meltwater).toEqual({ level: "yes", note: "add-on" });
    expect([g.brandwatch.level, g.sprinklr.level, g.talkwalker.level]).toEqual(["unknown", "unknown", "unknown"]);
  });
});

describe("rendered chart", () => {
  it("shows the legend, one table row per capability, the footnote and the sources", async () => {
    await mount();
    expect(Array.from(host!.querySelectorAll("[data-testid='chart-legend'] li")).map(li => li.textContent)).toEqual(["Yes", "Partial", "Unknown", "No", "Planned"]);
    expect(host!.querySelectorAll("[data-testid='chart-row']")).toHaveLength(11);
    expect(Array.from(host!.querySelectorAll("thead th")).map(th => th.textContent)).toEqual(["Capability", "XOOP", "Meltwater", "Brandwatch", "Sprinklr", "Talkwalker"]);
    expect(host!.querySelector("[data-testid='chart-footnote']")?.textContent).toBe(
      "Based on vendors' public documentation as of 10 November 2026. Unknown means we could not confirm it, not that it is absent.");
    expect(CHART_FOOTNOTE).toContain("10 November 2026");
    const links = Array.from(host!.querySelectorAll("details a")) as HTMLAnchorElement[];
    expect(links.length).toBeGreaterThan(10);
    expect(links.every(a => a.rel.includes("noopener") && a.target === "_blank")).toBe(true);
  });

  it("the optional rows can be left out", async () => {
    await mount(false);
    expect(host!.querySelectorAll("[data-testid='chart-row']")).toHaveLength(9);
    expect(host!.textContent).not.toContain("Hindi sentiment");
  });

  it("the visible wording avoids the banned words and percentages", async () => {
    await mount();
    const text = host!.textContent || "";
    for (const banned of [/\bonly\b/i, /real-time/i, /prediction/i, /stakeholder/i, /built for pr/i, /\b50\s?%/, /\b80\s?%/]) expect(text).not.toMatch(banned);
  });

  it("marks a Yes cell and a Unknown cell in the first rows", async () => {
    await mount();
    const row = host!.querySelectorAll("[data-testid='chart-row']")[1];     // Risk scoring with the reason shown
    const levels = Array.from(row.querySelectorAll("[data-level]")).map(e => e.getAttribute("data-level"));
    expect(levels).toEqual(["yes", "unknown", "unknown", "unknown", "unknown"]);
  });
});
