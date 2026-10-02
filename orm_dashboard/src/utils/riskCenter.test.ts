import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { riskStatsFromSummary } from "./brandEquity";
import {
  docSeverity, flaggedDocs, confidencePercent, confidenceTier, buildMatrix, legacyCellDocs,
  tilesFromSummary, sidebarRiskLevel, reasonSentence, formatScore, dateLabel, localDateKey,
  windowNote, unscoredNote, MATRIX_BANDS,
} from "./riskCenter";

const doc = (over: any = {}) => ({
  id: "d" + Math.random(), title: "t", scored: true, risk: 32, risk_exact: 32.23, risk_level: "MEDIUM",
  risk_sentiment: "Negative", timestamp: "2026-08-13T13:57:02+00:00", date_basis: "published",
  risk_explainability: { confidence: 0.5, topic_contribution: 0, sentiment_contribution: 40, individual_weights: { topic_weight: 0, sentiment_weight: 40 } },
  ...over,
});

describe("severity bands: one rule everywhere", () => {
  it("a 32 is MEDIUM", () => expect(docSeverity(doc())).toBe("MEDIUM"));

  it("uses the backend's unrounded band, not the rounded score", () => {
    // raw 25.3 rounds to 25 (LOW by the rounded number) but the engine bands it MEDIUM
    expect(docSeverity(doc({ risk: 25, risk_exact: 25.3, risk_level: "MEDIUM" }))).toBe("MEDIUM");
    expect(docSeverity(doc({ risk: 50, risk_exact: 50.2, risk_level: "HIGH" }))).toBe("HIGH");
    expect(docSeverity(doc({ risk: 75, risk_exact: 75.4, risk_level: "CRITICAL" }))).toBe("CRITICAL");
  });

  it("falls back to the 25/50/75 bands only when an older backend sent no level", () => {
    expect(docSeverity(doc({ risk_level: undefined, risk: 26 }))).toBe("MEDIUM");
    expect(docSeverity(doc({ risk_level: undefined, risk: 75 }))).toBe("HIGH");
    expect(docSeverity(doc({ risk_level: undefined, risk: 76 }))).toBe("CRITICAL");
  });

  it("an unscored document has no severity (never a 0)", () => {
    expect(docSeverity(doc({ scored: false, risk: 0, risk_level: null }))).toBeNull();
    expect(docSeverity(null)).toBeNull();
  });
});

describe("flaggedDocs", () => {
  it("keeps scored MEDIUM+ only, highest first", () => {
    const docs = [
      doc({ id: "low", risk: 20, risk_exact: 20, risk_level: "LOW" }),
      doc({ id: "unscored", scored: false, risk: 0, risk_level: null }),
      doc({ id: "m", risk: 33, risk_exact: 33.4 }),
      doc({ id: "h", risk: 60, risk_exact: 60, risk_level: "HIGH" }),
    ];
    expect(flaggedDocs(docs).map(d => d.id)).toEqual(["h", "m"]);
  });
  it("is empty (not an error) with no documents", () => {
    expect(flaggedDocs([])).toEqual([]);
    expect(flaggedDocs(undefined)).toEqual([]);
  });
});

describe("matrix: same bands as the table", () => {
  const flagged = flaggedDocs([
    doc({ id: "a", risk: 32, risk_exact: 32 }),
    doc({ id: "b", risk: 29, risk_exact: 29 }),
    doc({ id: "c", risk: 60, risk_exact: 60, risk_level: "HIGH" }),
    doc({ id: "d", risk: 90, risk_exact: 90, risk_level: "CRITICAL", risk_explainability: { confidence: 0.9 } }),
  ]);

  it("rows are the severity bands, highest first (no LOW row)", () => {
    expect(MATRIX_BANDS).toEqual(["CRITICAL", "HIGH", "MEDIUM"]);
  });

  it("a MEDIUM item is never under a HIGH/CRITICAL row (and vice versa)", () => {
    const m = buildMatrix(flagged);
    for (const band of MATRIX_BANDS) {
      for (const col of ["LOW", "MEDIUM", "HIGH"] as const) {
        for (const d of m.grid[band][col]) expect(d.severity).toBe(band);
      }
    }
  });

  it("cell counts add up to the number of flagged documents (the table)", () => {
    const m = buildMatrix(flagged);
    let n = 0;
    for (const band of MATRIX_BANDS) for (const col of ["LOW", "MEDIUM", "HIGH"] as const) n += m.grid[band][col].length;
    expect(n + m.unplaced).toBe(flagged.length);
    expect(m.grid.MEDIUM.MEDIUM).toHaveLength(2);
    expect(m.grid.HIGH.MEDIUM).toHaveLength(1);
    expect(m.grid.CRITICAL.HIGH).toHaveLength(1);
  });

  it("different confidence gives a different column", () => {
    expect(confidenceTier(32)).toBe("LOW");
    expect(confidenceTier(33)).toBe("MEDIUM");
    expect(confidenceTier(66)).toBe("MEDIUM");
    expect(confidenceTier(67)).toBe("HIGH");
  });

  it("an article with no confidence value is reported, never placed as 0%", () => {
    const f = flaggedDocs([doc({ risk_explainability: {} }), doc({ risk_explainability: null })]);
    const m = buildMatrix(f);
    expect(m.unplaced).toBe(2);
    expect(m.grid.MEDIUM.LOW).toHaveLength(0);
    expect(confidencePercent(f[0])).toBeNull();
  });

  it("legacy Executive-Analytics deep links keep their own score tiers", () => {
    const f = flaggedDocs([doc({ risk: 33, risk_exact: 33 }), doc({ risk: 32, risk_exact: 32 })]);
    expect(legacyCellDocs(f, "MEDIUM", "MEDIUM")).toHaveLength(1);
    expect(legacyCellDocs(f, "LOW", "MEDIUM")).toHaveLength(1);
  });
});

describe("tiles from the server summary", () => {
  const block = { visible_documents: 646, scored_documents: 624, unscored_documents: 22, total: 14, critical: 0, high: 0, medium: 14, average: 31, highest: 33, as_of: "2026-10-02T10:00:00+00:00", top: [] };

  it("maps flagged / severity / highest / unscored / as-of from the server block", () => {
    expect(tilesFromSummary(riskStatsFromSummary(block))).toEqual({
      flagged: 14, critical: 0, high: 0, medium: 14, highest: 33, unscored: 22, asOf: "2026-10-02T10:00:00+00:00",
    });
  });

  it("zero incidents: highest is null (shown as a dash), not 0", () => {
    const t = tilesFromSummary(riskStatsFromSummary({ ...block, total: 0, medium: 0, average: null, highest: null }))!;
    expect(t.flagged).toBe(0);
    expect(t.highest).toBeNull();
  });

  it("missing block -> unavailable (null), never zeros", () => {
    expect(tilesFromSummary(riskStatsFromSummary(undefined))).toBeNull();
    expect(tilesFromSummary(riskStatsFromSummary({}))).toBeNull();
  });

  it("counts do not depend on how many documents the table was given (500 cap)", () => {
    const small = tilesFromSummary(riskStatsFromSummary(block))!.flagged;
    // the table may only hold 500 articles; the tile still reports the server total
    expect(small).toBe(14);
    expect(windowNote(10, small)).toBe("Showing the 10 most recent of 14 flagged articles.");
    expect(windowNote(14, small)).toBeNull();
    expect(windowNote(3, null)).toBeNull();
  });

  it("unchecked articles note appears only when there are some", () => {
    expect(unscoredNote(22)).toBe("22 articles have not been risk-checked yet and are not counted.");
    expect(unscoredNote(1)).toBe("1 article has not been risk-checked yet and is not counted.");
    expect(unscoredNote(0)).toBeNull();
    expect(unscoredNote(undefined)).toBeNull();
  });
});

describe("sidebar risk level", () => {
  const stats = (o: any) => riskStatsFromSummary({ total: o.c + o.h + o.m, critical: o.c, high: o.h, medium: o.m, average: 30, highest: 30, visible_documents: 10, scored_documents: 10, unscored_documents: 0, top: [] });

  it("no incidents -> NO INCIDENTS (not LOW, not green-by-default)", () => {
    expect(sidebarRiskLevel(false, null, stats({ c: 0, h: 0, m: 0 }))).toBe("NO INCIDENTS");
  });
  it("medium / high / critical follow the highest band present", () => {
    expect(sidebarRiskLevel(false, null, stats({ c: 0, h: 0, m: 22 }))).toBe("MEDIUM");
    expect(sidebarRiskLevel(false, null, stats({ c: 0, h: 1, m: 22 }))).toBe("HIGH");
    expect(sidebarRiskLevel(false, null, stats({ c: 1, h: 1, m: 22 }))).toBe("CRITICAL");
  });
  it("loading, error and a missing block are UNAVAILABLE, never LOW", () => {
    expect(sidebarRiskLevel(true, null, stats({ c: 0, h: 0, m: 0 }))).toBe("UNAVAILABLE");
    expect(sidebarRiskLevel(false, "Telemetry Offline", stats({ c: 0, h: 0, m: 0 }))).toBe("UNAVAILABLE");
    expect(sidebarRiskLevel(false, null, null)).toBe("UNAVAILABLE");
  });
  it("matches the page: 22 Medium articles show MEDIUM (it used to read LOW)", () => {
    expect(sidebarRiskLevel(false, null, stats({ c: 0, h: 0, m: 22 }))).not.toBe("LOW");
  });
});

describe("drawer sentence", () => {
  it("is plain: no raw floats, no 'None', no engine words", () => {
    const s = reasonSentence(doc())!;
    expect(s).toBe("Flagged because the article's tone is negative. Rated Medium (32.2/100).");
    expect(s).not.toMatch(/\d\.\d{3,}/);
    expect(s).not.toMatch(/None|weight|modifier|topic '/i);
  });
  it("mentions a risky subject only when topic actually contributed", () => {
    const withTopic = reasonSentence(doc({ risk_explainability: { confidence: 0.6, topic_contribution: 90, individual_weights: { topic_weight: 90, sentiment_weight: 40 } } }))!;
    expect(withTopic).toContain("high-risk subject");
    expect(reasonSentence(doc())).not.toContain("subject");
  });
  it("shows nothing invented when the data is missing", () => {
    expect(reasonSentence(doc({ risk_explainability: null }))).toBeNull();
    expect(reasonSentence(doc({ risk_sentiment: null, risk_explainability: { topic_contribution: 0 } }))).toBeNull();
    expect(reasonSentence(doc({ scored: false }))).toBeNull();
  });
  it("scores show at most one decimal", () => {
    expect(formatScore(32)).toBe("32");
    expect(formatScore(32.23)).toBe("32.2");
    expect(formatScore(33.06)).toBe("33.1");
  });

  it("the shown score never contradicts its band (edges 25 / 50 / 75)", () => {
    const bandOf = (n: number) => (n <= 25 ? "LOW" : n <= 50 ? "MEDIUM" : n <= 75 ? "HIGH" : "CRITICAL");
    // strictly above an edge: never shown as the edge itself
    expect(formatScore(25.3)).toBe("25.3");
    expect(formatScore(25.04)).toBe("25.04");
    expect(formatScore(25.004)).toBe("25.01");
    expect(formatScore(50.02)).toBe("50.02");
    expect(formatScore(75.001)).toBe("75.01");
    // at or below an edge: shown as is, band is the lower one
    expect(formatScore(25)).toBe("25");
    expect(formatScore(24.96)).toBe("25");
    expect(formatScore(50)).toBe("50");
    // property: for many raw scores the displayed number is in the same band as the raw one
    for (let raw = 20; raw <= 80; raw += 0.0137) {
      const shown = Number(formatScore(raw));
      expect(bandOf(shown), `raw ${raw} shown ${shown}`).toBe(bandOf(raw));
    }
  });
});

describe("dates", () => {
  it("labels a collected-date fallback", () => {
    expect(dateLabel(doc({ date_basis: "collected" }), "en-US").collected).toBe(true);
    expect(dateLabel(doc(), "en-US").collected).toBe(false);
    expect(dateLabel({}, "en-US")).toEqual({ text: "N/A", collected: false });
  });
  it("date filter keys include the year", () => {
    const a = localDateKey("2026-10-01T12:00:00");
    const b = localDateKey("2024-10-01T12:00:00");
    expect(a).toMatch(/^2026-10-01$/);
    expect(a).not.toBe(b);
    expect(localDateKey(null)).toBeNull();
    expect(localDateKey("garbage")).toBeNull();
  });
});

describe("Risk Center wording (static guard)", () => {
  const SRC = path.resolve(__dirname, "..");
  const stripComments = (t: string) => t.replace(/\{\/\*[\s\S]*?\*\/\}/g, "").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
  const tab = stripComments(readFileSync(path.resolve(SRC, "components/RiskTab.tsx"), "utf-8"));
  const defs = stripComments(readFileSync(path.resolve(SRC, "lib/metricDefinitions.tsx"), "utf-8"));
  const flaggedDef = defs.slice(defs.indexOf("export function FlaggedArticlesDefinition"), defs.indexOf("export function DocumentsAnalyzedDefinition"));
  const critDef = defs.slice(defs.indexOf("export function CriticalRisksVsActiveAlertsDefinition"), defs.indexOf("export function RiskSeverityDefinition"));

  it("the page never calls confidence 'likelihood' or 'impact', and has no Low tile / topic categories", () => {
    // the legacy ?likelihood= URL param (read for Executive Analytics deep links) is the only allowed mention
    expect(tab.replace(/likelihoodParam|"likelihood"/g, "")).not.toMatch(/likelihood/i);
    expect(tab).not.toMatch(/IMPACT/);
    expect(tab).not.toMatch(/Low Risks|Incident Categories|Core Topic|Impact Score/);
  });
  it("executive-facing text has no file names, no '75+', no raw engine words", () => {
    for (const t of [tab, flaggedDef, critDef]) {
      expect(t).not.toMatch(/risk_config|\.py\b|TOPIC_WEIGHTS/);
      expect(t).not.toMatch(/75\+/);
    }
    expect(critDef).toContain("above {HIGH_MAX}");
  });
  it("states the counting unit as articles", () => {
    expect(tab).toContain("Flagged Articles");
    expect(flaggedDef).toMatch(/articles/);
  });
  it("makes the time window explicit and never says 'current' about all-time counts", () => {
    const side = stripComments(readFileSync(path.resolve(SRC, "components/Sidebar.tsx"), "utf-8"));
    expect(tab).toContain("all-time counts");
    expect(side).toContain("Highest severity flagged (all time)");
    expect(side).not.toContain("Current Risk Level");
    for (const t of [tab, side, flaggedDef, critDef]) {
      expect(t.replace(/\.current|currentTarget|currentUser/g, "")).not.toMatch(/current(ly)?/i);
    }
  });
  it("unavailable data says Unavailable", () => {
    expect(tab).toContain('risk_sentiment ?? "Unavailable"');
    expect(tab).toContain('conf === null ? "Unavailable"');
    expect(tab).not.toContain("Not available");
  });
  it("only AI-generated text is labelled AI", () => {
    expect(tab).not.toMatch(/>\s*AI Summary/);
    expect(tab).toContain("Suggested next step (AI-generated)");
    expect(tab).toContain("Why this was flagged");
  });
});
