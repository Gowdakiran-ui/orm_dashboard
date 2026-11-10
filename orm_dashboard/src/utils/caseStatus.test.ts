import { describe, it, expect } from "vitest";
import {
  CASE_STATUS_LABEL, caseStatusOf, statusSentence, incidentBlockFromSummary, collapseByIncident, incidentBadgeText, documentsNote,
  type IncidentItem,
} from "./caseStatus";
import { riskStatsFromSummary } from "./brandEquity";
import { reasonSentence } from "./riskCenter";

const doc = (id: string, over: any = {}) => ({
  id, title: `title ${id}`, scored: true, risk: 51, risk_exact: 51, risk_level: "HIGH", risk_sentiment: "Negative",
  risk_explainability: { confidence: 0.5, topic_contribution: 0, individual_weights: { topic_weight: 0, sentiment_weight: 40 } },
  ...over,
});
const withStatus = (status: any, extra: any = {}) => ({ risk_explainability: { confidence: 0.5, topic_contribution: 0, case_status: status, ...extra } });

describe("status label", () => {
  it("reads the seven stored labels and nothing else", () => {
    for (const s of Object.keys(CASE_STATUS_LABEL)) expect(caseStatusOf(doc("a", withStatus(s)))).toBe(s);
    expect(caseStatusOf(doc("a", withStatus("guilty")))).toBeNull();
    expect(caseStatusOf(doc("a"))).toBeNull();
    expect(caseStatusOf(null)).toBeNull();
  });

  it("uses plain wording for each label", () => {
    expect(CASE_STATUS_LABEL.penalty_or_order).toBe("Penalty / order");
    expect(CASE_STATUS_LABEL.dismissed_or_closed).toBe("Dismissed / closed");
  });

  it("states the stage in the why-flagged text, and says so when the score was held at Medium", () => {
    expect(statusSentence(doc("a", withStatus("probe")))).toBe("The story is at the probe stage.");
    expect(statusSentence(doc("a", withStatus("settled", { case_status_cap_applied: true }))))
      .toBe("The story is at the settled stage. Stories at this stage are held at Medium and do not reach High.");
    expect(statusSentence(doc("a"))).toBeNull();
  });

  it("appends the stage to the existing reason sentence and leaves it unchanged without a label", () => {
    const plain = reasonSentence(doc("a"))!;
    expect(plain).toBe("Flagged because the article's tone is negative. Rated High (51/100).");
    expect(reasonSentence(doc("a", withStatus("charged")))).toBe(`${plain} The story is at the charged stage.`);
  });
});

const item = (id: string, docIds: string[], over: Partial<IncidentItem> = {}): IncidentItem => ({
  id, title: "t", severity: "HIGH", score: 51, status: "charged", documents: docIds.length, sources: docIds.length, docIds, ...over,
});

describe("incident rows", () => {
  it("one row per incident, led by the strongest loaded document; the rest hang off it", () => {
    const flagged = [doc("a", { risk: 79 }), doc("b"), doc("c"), doc("d", { risk: 40 })];     // already sorted by score
    const rows = collapseByIncident(flagged, [item("i1", ["a", "b", "c"], { documents: 5, sources: 4 })]);
    expect(rows.map(r => r.id)).toEqual(["a", "d"]);
    expect(rows[0].incident).toMatchObject({ id: "i1", documents: 5, sources: 4 });
    expect(rows[0].incident.others.map((o: any) => o.id)).toEqual(["b", "c"]);
    expect(rows[1].incident).toBeNull();
  });

  it("without incidents every document is its own row (older server)", () => {
    expect(collapseByIncident([doc("a"), doc("b")], null).map(r => r.id)).toEqual(["a", "b"]);
    expect(collapseByIncident([doc("a")], [])[0].incident).toBeNull();
  });

  it("an incident whose lead is outside the loaded window is led by its first loaded member", () => {
    const rows = collapseByIncident([doc("b"), doc("c")], [item("i1", ["a", "b", "c"], { documents: 3 })]);
    expect(rows.map(r => r.id)).toEqual(["b"]);
    expect(rows[0].incident.documents).toBe(3);
  });

  it("badge words: sources when several outlets, articles when one outlet, nothing for a single document", () => {
    expect(incidentBadgeText({ documents: 9, sources: 7 })).toBe("7 sources");
    expect(incidentBadgeText({ documents: 3, sources: 1 })).toBe("3 articles");
    expect(incidentBadgeText({ documents: 1, sources: 1 })).toBeNull();
    expect(incidentBadgeText(null)).toBeNull();
    expect(documentsNote(1)).toBe("1 document");
    expect(documentsNote(5)).toBe("5 documents");
  });
});

describe("incidents block from the server", () => {
  const block = { total: 22, critical: 3, high: 4, medium: 15, highest: 79, average: 40, top: [], medium_: 0,
    incidents: { total: 6, critical: 1, high: 2, medium: 3, items: [
      { id: "i1", title: "ED chargesheet", severity: "CRITICAL", score: 79, status: "charged", documents: 9, sources: 7, doc_ids: ["a", "b"] },
      { id: "bad", title: "x", severity: "WEIRD", documents: 1, doc_ids: [] },
      { title: "no id" },
    ] } };

  it("parses well-formed items and drops malformed ones", () => {
    const b = incidentBlockFromSummary(block)!;
    expect(b).toMatchObject({ total: 6, critical: 1, high: 2, medium: 3 });
    expect(b.items).toHaveLength(1);
    expect(b.items[0]).toMatchObject({ id: "i1", status: "charged", documents: 9, sources: 7, docIds: ["a", "b"] });
  });

  it("is null when absent or malformed", () => {
    expect(incidentBlockFromSummary({})).toBeNull();
    expect(incidentBlockFromSummary({ incidents: { total: 1 } })).toBeNull();
    expect(incidentBlockFromSummary(null)).toBeNull();
  });

  it("riskStatsFromSummary keeps the per-document counts and adds the incident headline", () => {
    const s = riskStatsFromSummary({ ...block, medium: 15, critical: 3, high: 4, total: 22 })!;
    expect(s).toMatchObject({ critical: 3, high: 4, medium: 15, dangerCount: 7, dangerIncidents: 3 });
    expect(riskStatsFromSummary({ total: 1, critical: 0, high: 0, medium: 1 })!.dangerIncidents).toBeNull();
  });
});

describe("small-penalty rule wording", () => {
  it("says why a small or old penalty is held at Medium, using the stored reason", () => {
    const d = doc("p", withStatus("penalty_or_order", { penalty_cap_applied: true, penalty_cap_reason: "a penalty under 25 lakh rupees from a consumer commission, state RERA or municipal body" }));
    expect(statusSentence(d)).toBe("The story is at the penalty / order stage. Held at Medium: a penalty under 25 lakh rupees from a consumer commission, state RERA or municipal body.");
    expect(reasonSentence(d)).toContain("Held at Medium: a penalty under 25 lakh rupees");
  });

  it("a penalty that keeps its score gets only the stage; a missing reason falls back to plain words", () => {
    expect(statusSentence(doc("p", withStatus("penalty_or_order", { penalty_cap_applied: false, penalty_cap_reason: "the amount is 25 lakh rupees or more" })))).toBe("The story is at the penalty / order stage.");
    expect(statusSentence(doc("p", withStatus("penalty_or_order", { penalty_cap_applied: true })))).toBe("The story is at the penalty / order stage. Held at Medium: it is a small or old order.");
    // user-generated / video allegation rule
    const ugc = "an allegation from a user-generated or video source (16,337 views, under 100,000) that is not a news outlet";
    expect(statusSentence(doc("u", withStatus("allegation", { ugc_cap_applied: true, ugc_cap_reason: ugc })))).toBe(`The story is at the allegation stage. Held at Medium: ${ugc}.`);
    expect(statusSentence(doc("u", withStatus("allegation", { ugc_cap_applied: true })))).toBe("The story is at the allegation stage. Held at Medium: it is an allegation from a low-reach user-generated or video source.");
    expect(statusSentence(doc("u", withStatus("allegation", { ugc_cap_applied: false, ugc_cap_reason: "100,000 views or more" })))).toBe("The story is at the allegation stage.");
  });
});
