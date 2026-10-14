import { describe, it, expect } from "vitest";
import { buildRiskHeatmap } from "./riskHeatmap";
import { buildMatrix, flaggedDocs } from "./riskCenter";

// Same fields /documents/client/{id} sends: `risk` is the rounded score, `risk_level` is the band of the unrounded one.
const doc = (topic: string, exact: number | null, level: string | null, over: any = {}) => ({
  id: `${topic}-${exact}-${Math.random()}`, topic, sentiment: 0.1,
  scored: exact !== null, risk: exact === null ? 0 : Math.round(exact), risk_exact: exact, risk_level: level,
  risk_explainability: { confidence: 0.5 }, ...over,
});
const levelTotals = (h: ReturnType<typeof buildRiskHeatmap>) => {
  const t: Record<string, number> = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 };
  h.categories.forEach(c => h.severities.forEach(s => { t[s] += h.grid[c][s].count; }));
  return t;
};
const many = (topic: string, n: number, exact: number, level: string) => Array.from({ length: n }, () => doc(topic, exact, level));

describe("Threat Heatmap bands with the server risk_level, like Risk Center's tiles and matrix", () => {
  it("puts a 25.4 score (rounds to 25) in MEDIUM, as the server says, not LOW", () => {
    const h = buildRiskHeatmap([...many("Legal", 4, 5, "LOW"), doc("Legal", 25.4, "MEDIUM")], 5);
    expect(h.grid.Legal.MEDIUM.count).toBe(1);
    expect(h.grid.Legal.LOW.count).toBe(4);
  });
  it("same for the other band edges (50.4 -> HIGH, 75.4 -> CRITICAL)", () => {
    const h = buildRiskHeatmap([...many("T", 3, 5, "LOW"), doc("T", 50.4, "HIGH"), doc("T", 75.4, "CRITICAL")], 5);
    expect(h.grid.T.HIGH.count).toBe(1);
    expect(h.grid.T.CRITICAL.count).toBe(1);
  });
  it("leaves unscored articles out of every cell, Low included", () => {
    const docs = [...many("T", 5, 3, "LOW"), doc("T", null, null), doc("T", null, null)];
    const h = buildRiskHeatmap(docs, 5);
    expect(levelTotals(h)).toEqual({ LOW: 5, MEDIUM: 0, HIGH: 0, CRITICAL: 0 });
  });
  it("only the unscored articles leave the Low column; no other cell changes", () => {
    const scored = [...many("A", 6, 3, "LOW"), ...many("A", 2, 30, "MEDIUM"), ...many("B", 5, 2, "LOW"), doc("B", 80, "CRITICAL")];
    const withUnscored = [...scored, doc("A", null, null), doc("B", null, null), doc("B", null, null)];
    const a = buildRiskHeatmap(scored, 5), b = buildRiskHeatmap(withUnscored, 5);
    expect(b.grid).toEqual(a.grid);
  });
  it("Medium/High/Critical totals equal the Risk Matrix counts (no topic below the floor, every flagged article has a confidence)", () => {
    const docs = [
      ...many("A", 6, 3, "LOW"), ...many("A", 3, 30, "MEDIUM"), doc("A", 60, "HIGH"),
      ...many("B", 5, 2, "LOW"), doc("B", 80, "CRITICAL"), doc("B", 25.4, "MEDIUM"), doc("B", null, null),
    ];
    const t = levelTotals(buildRiskHeatmap(docs, 5));
    const m = buildMatrix(flaggedDocs(docs));
    const count = (row: "MEDIUM" | "HIGH" | "CRITICAL") => Object.values(m.grid[row]).flat().length;
    expect(t.MEDIUM).toBe(count("MEDIUM"));
    expect(t.HIGH).toBe(count("HIGH"));
    expect(t.CRITICAL).toBe(count("CRITICAL"));
  });
});
