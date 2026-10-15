import { describe, it, expect } from "vitest";
import { buildExecutiveSummary, NOT_ENOUGH_DATA, TOP_RISKS_SHOWN, OPEN_ALERTS_SHOWN, TOP_TOPICS_SHOWN } from "./executiveSummary";
import { buildReportModel, type ReportFacts } from "./reportModel";
import { input, summary, mkDocs, analyticsFor, hist } from "./reportTestFixtures";

const TREND = /improv|declin|rising|falling|trend|up since|down since|increas|decreas|worsen/i;
const summaryOf = (over = {}) => { const m = buildReportModel(input(over)); return { m, s: buildExecutiveSummary(m.facts, m.meta.clientName) }; };

describe("executive summary: full data", () => {
  const { m, s } = summaryOf();
  it("six KPI cards built from the model values", () => {
    expect(s.kpis.map(k => k.label)).toEqual(["Reputation Score", "Risk Signals", "Flagged Articles", "Active Alerts", "Overall Tone", "Documents Analyzed"]);
    expect(s.kpis[0]).toMatchObject({ value: "75.51", sub: "Grade B" });
    expect(s.kpis[1].value).toBe("5");
    expect(s.kpis[2]).toMatchObject({ value: "14", sub: "2 Critical · 3 High · 9 Medium" });
    expect(s.kpis[3].value).toBe("2");
    expect(s.kpis[4].value).toBe("neutral");
    expect(s.kpis[5].value).toBe("140");
  });
  it("3 to 5 template sentences, from model values, with no trend language", () => {
    expect(s.sentences.length).toBeGreaterThanOrEqual(3);
    expect(s.sentences.length).toBeLessThanOrEqual(5);
    expect(s.sentences.join(" ")).toContain("14 articles carry a risk above Low: 2 Critical, 3 High and 9 Medium.");
    expect(s.sentences.join(" ")).toContain("There are 2 open alerts.");
    expect(s.sentences.join(" ")).toContain(m.facts.texts.overview);
    for (const t of [...s.sentences, ...s.kpis.map(k => `${k.label} ${k.value} ${k.sub}`)]) expect(t).not.toMatch(TREND);
  });
  it("truncates to the top 3 risks, 3 alerts and 3 topics, and says how many more", () => {
    expect(s.topRisks).toHaveLength(TOP_RISKS_SHOWN);
    expect(s.topRisks[0].severity).toBe("CRITICAL");
    expect(s.topRisksNote).toBe(`+${m.facts.topRisks.length - 3} more in the Risk Center`);
    expect(s.topTopics).toHaveLength(TOP_TOPICS_SHOWN);
    const many = { ...m.facts, alerts: { state: "ok" as const, items: Array.from({ length: 5 }, (_, i) => ({ severity: "HIGH", title: `A${i}`, alertType: "t", raised: "x", what: null, when: null, nextStep: null })) } };
    const s2 = buildExecutiveSummary(many, "Acme");
    expect(s2.openAlerts).toHaveLength(OPEN_ALERTS_SHOWN);
    expect(s2.openAlertsNote).toBe("+2 more in the Risk Center");
  });
  it("names the highest-risk article by score order", () => {
    expect(s.sentences.join(" ")).toContain(`"${m.facts.topRisks[0].title}" (${m.facts.topRisks[0].score} pts, Critical)`);
  });
});

describe("executive summary: honest empty, N/A and unavailable states", () => {
  it("nothing risk-scored yet reads N/A, never zero", () => {
    const { s } = summaryOf({ reputationSummary: summary({ document_risk: { visible_documents: 10, scored_documents: 0, unscored_documents: 10, total: 0, critical: 0, high: 0, medium: 0 } }) });
    expect(s.kpis[1].value).toBe("N/A");
    expect(s.kpis[2].value).toBe("N/A");
    expect(s.sentences.join(" ")).toContain("No articles have been risk-scored yet");
  });
  it("a client with nothing flagged says so plainly", () => {
    const documents = mkDocs(30, () => ({ scored: true, risk: 0, risk_exact: 0, risk_level: "LOW" }));
    const { s } = summaryOf({ documents, analytics: analyticsFor(documents, [], hist), alerts: [], reputationSummary: summary({ document_risk: { visible_documents: 30, scored_documents: 30, unscored_documents: 0, total: 0, critical: 0, high: 0, medium: 0, average: 0, highest: null } }) });
    expect(s.sentences.join(" ")).toContain("No articles carry a risk above Low.");
    expect(s.sentences.join(" ")).toContain("There are no open alerts.");
    expect(s.topRisksNote).toBe("No flagged articles.");
    expect(s.openAlertsNote).toBe("No open alerts.");
  });
  it("failed sections show Unavailable, not zeros", () => {
    const { s } = summaryOf({ reputationSummary: null, reputationSummaryError: "x", documentsError: "x", alertsError: "x", documents: [], alerts: [], analytics: analyticsFor([], [], []) });
    expect(s.kpis.map(k => k.value)).toEqual(["Unavailable", "Unavailable", "Unavailable", "Unavailable", "Unavailable", "Unavailable"]);
    expect(s.topRisksNote).toMatch(/^Unavailable/);
    expect(s.openAlertsNote).toMatch(/^Unavailable/);
    expect(s.topicsNote).toMatch(/^Unavailable/);
    expect(s.tone).toBeNull();
    expect(s.sentences.join(" ")).not.toMatch(/\b0 (articles|alerts)/);
  });
  it("unknown score: states it is not available yet", () => {
    const { s } = summaryOf({ reputationSummary: summary({ reputation: { score: null, grade: null, status: "insufficient_evidence", computed_at: null } }) });
    expect(s.headline.known).toBe(false);
    expect(s.sentences[0]).toContain("Not enough evidence to score yet");
    expect(NOT_ENOUGH_DATA).toBe("Not enough data yet");
  });
  it("malformed numbers never reach a sentence", () => {
    const { s } = summaryOf({ reputationSummary: summary({ document_risk: { visible_documents: 140, scored_documents: 135, unscored_documents: 5, total: Number.NaN, critical: 2, high: 3, medium: 9 } }) });
    expect(s.sentences.join(" ")).not.toMatch(/NaN|undefined|null|Infinity/);
    expect(s.kpis[2].value).toBe("N/A");
  });
  it("is a pure function of its input", () => {
    const f = buildReportModel(input()).facts as ReportFacts;
    expect(buildExecutiveSummary(f, "Acme")).toEqual(buildExecutiveSummary(structuredClone(f), "Acme"));
  });
});
