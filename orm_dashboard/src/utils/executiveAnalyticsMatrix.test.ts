import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { buildMatrix, flaggedDocs } from "./riskCenter";

const SRC = path.resolve(__dirname, "..");
const strip = (t: string) => t.replace(/\{\/\*[\s\S]*?\*\/\}/g, "").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const read = (rel: string) => strip(readFileSync(path.resolve(SRC, rel), "utf-8"));

// Same shape useAnalytics.riskMatrixData hands the Executive Analytics panel: the document plus name/impact/z.
const item = (risk: number, level: string, conf: number | null, over: any = {}) => ({
  id: `d-${risk}-${conf}`, title: "t", scored: true, risk, risk_exact: risk + 0.2, risk_level: level,
  risk_explainability: conf === null ? {} : { confidence: conf },
  name: "t", impact: risk, z: risk * 2, ...over,
});

describe("Executive Analytics matrix uses the platform bands (25/50/75) and Confidence", () => {
  const data = [
    item(30, "MEDIUM", 0.5), item(60, "HIGH", 0.9), item(90, "CRITICAL", 0.1), item(40, "MEDIUM", 0.7),
    item(10, "LOW", 0.9),                       // not flagged: never in the matrix
    item(35, "MEDIUM", null),                   // flagged but no confidence: not placed, never shown as Low
    item(0, "LOW", 0.5, { scored: false }),     // never scored: never in the matrix
  ];
  const m = buildMatrix(flaggedDocs(data));

  it("places a 30 in Medium (the old 33/67 tiers called it Low) and a 60 in High", () => {
    expect(m.grid.MEDIUM.MEDIUM).toHaveLength(1);
    expect(m.grid.HIGH.HIGH).toHaveLength(1);
    expect(m.grid.CRITICAL.LOW).toHaveLength(1);
    expect(m.grid.MEDIUM.HIGH).toHaveLength(1);
  });
  it("leaves out LOW and unscored documents, and reports flagged documents without a confidence as not placed", () => {
    const placed = Object.values(m.grid).flatMap(r => Object.values(r)).flat();
    expect(placed).toHaveLength(4);
    expect(m.unplaced).toBe(1);
  });
  it("cell totals plus not-placed equal the number of flagged documents (what Risk Center's tile counts)", () => {
    const placed = Object.values(m.grid).flatMap(r => Object.values(r)).flat().length;
    expect(placed + m.unplaced).toBe(flaggedDocs(data).length);
  });
});

describe("Executive Analytics matrix wording and links (static guard)", () => {
  const panel = read("components/RiskAnalyticsPanel.tsx");
  const hook = read("hooks/useAnalytics.ts");
  it("is built with Risk Center's builder and links with band/confidence", () => {
    expect(panel).toContain("buildMatrix(flaggedDocs(riskMatrixData))");
    expect(panel).toContain('navigateTo("risk", { band: rowKey, confidence: colKey })');
  });
  it("calls the axes Severity and Confidence, never Impact or Likelihood", () => {
    expect(panel).toContain("Risk by Severity & Confidence");
    expect(panel).toContain("LOW CONFIDENCE");
    expect(panel).not.toMatch(/likelihood|>IMPACT<|Impact:|Impact &/i);
    expect(hook).not.toMatch(/likelihood/i);
  });
  it("never turns a missing confidence into a 0", () => {
    expect(hook).not.toMatch(/confidence \?\? 0/);
  });
});

describe("Brand Equity 'Total Risks Tracked' says all time", () => {
  it("label and definition", () => {
    expect(read("components/ReputationSummaryCard.tsx")).toContain('label: "Total Risks Tracked (all time)"');
    expect(read("lib/metricDefinitions.tsx")).toMatch(/all time, not a recent window/);
    expect(read("lib/metricDefinitions.tsx")).not.toContain("currently-tracked");
  });
});

describe("Landing page makes no forward-looking or trend claims (static guard)", () => {
  const page = readFileSync(path.resolve(SRC, "app/page.tsx"), "utf-8");
  it.each([
    /what(&apos;|')s likely next/i, /before it becomes a headline/i, /before it(&apos;|')s a headline/i, /what(&apos;|')s changing/i,
    /rising risk/i, /sentiment shift/i, /emerging (alert|issue)/i, /spot reputation shifts early/i, /run-up to a listing/i,
    /trend direction/i, /improving, stable/i, /trending in a direction/i, /what(&apos;|')s next is already/i, /still time to respond/i,
    /before it has time to compound/i, /predictive/i,
  ])("does not contain %s", (re) => {
    expect(page).not.toMatch(re);
  });
});
