import { describe, it, expect } from "vitest";
import { windowPhrase, windowDays } from "./windowText";
import { noScoreReason, trackedCardView, orderTrackedExecutives, noCoverageLine } from "./executivesView";
import { buildCompetitorCards, notEnoughCoverageMessage, evidenceCaption, competitorCardView, placeholderCardView } from "./competitorCompare";

describe("window text", () => {
  it("uses the row's window and 30 days when the row predates the setting", () => {
    expect(windowPhrase(365)).toBe("last 365 days");
    expect(windowPhrase(90)).toBe("last 90 days");
    expect(windowPhrase(undefined)).toBe("last 30 days");
    expect(windowPhrase(null)).toBe("last 30 days");
    expect(windowDays(0)).toBe(30);
  });
  it("executive sentences show the window", () => {
    expect(noScoreReason({ articles_all_time: 9, latest_article_at: "2025-08-04T07:00:00+00:00", window_days: 365 }, "Godrej Properties"))
      .toContain("but none in the last 365 days (newest 04-08-2025)");
    expect(noScoreReason({ articles_all_time: 0, window_days: 365 }, "Godrej")).toContain("nothing to score");
    expect(noScoreReason({ window_days: 365 }, "Godrej")).toContain("in the last 365 days");
    expect(noScoreReason({ articles_all_time: 3 }, "Godrej")).toContain("last 30 days");           // old row: unchanged wording
    expect(trackedCardView({ score: 71.2, grade: "B", health_status: "COMPLETE", document_count: 6, window_days: 365 }, "Godrej").detail).toContain("6 articles in the last 365 days");
    expect(noCoverageLine("Godrej", 365)).toContain("published in the last 365 days");
  });
});

describe("orderTrackedExecutives", () => {
  const tracked = [
    { entity_id: "p1", name: "Pirojsha Godrej", score: 60, grade: "C", health_status: "COMPLETE", document_count: 5 },
    { entity_id: "p2", name: "Geetika Trehan", score: 80, grade: "B", health_status: "COMPLETE", document_count: 9 },
    { entity_id: "p3", name: "Karishma Rane", score: 0, health_status: "INSUFFICIENT_EVIDENCE", document_count: 0 },
  ];
  const seeded = [
    { entity_id: "p4", name: "Rajendra Khetawat", rank: 3, role: "CFO" },
    { entity_id: "p1", name: "Pirojsha Godrej", rank: 1, role: "Chairperson" },
    { entity_id: "p5", name: "Gaurav Pandey", rank: 2, role: "MD & CEO" },
  ];
  it("without a seeded list it is the previous behaviour (scored first, highest score first)", () => {
    const out = orderTrackedExecutives(tracked, null);
    expect(out.map(o => o.row.name)).toEqual(["Geetika Trehan", "Pirojsha Godrej", "Karishma Rane"]);
    expect(out.every(o => !o.seeded && !o.alsoTracked && !o.placeholder)).toBe(true);
  });
  it("seeded leaders come first in rank order, with a stand-in for anyone without a score row, then 'also tracked'", () => {
    const out = orderTrackedExecutives(tracked, seeded);
    expect(out.map(o => o.row.name)).toEqual(["Pirojsha Godrej", "Gaurav Pandey", "Rajendra Khetawat", "Geetika Trehan", "Karishma Rane"]);
    expect(out.map(o => o.seedRole)).toEqual(["Chairperson", "MD & CEO", "CFO", null, null]);
    expect(out.map(o => o.placeholder)).toEqual([false, true, true, false, false]);
    expect(out.map(o => o.alsoTracked)).toEqual([false, false, false, true, true]);
    const standIn = out[1].row;
    expect(standIn.health_status).toBe("NO_SCORE_YET");
    expect(trackedCardView(standIn, "Godrej Properties").headline).toBe("No score yet");              // never a zero or a grade
  });
  it("a seeded person is not repeated under 'also tracked'", () => {
    const names = orderTrackedExecutives(tracked, seeded).map(o => o.row.name);
    expect(new Set(names).size).toBe(names.length);
  });
});

describe("competitor cards", () => {
  const rows = [
    { competitor_id: "c1", competitor_name: "Lodha", rank: 1, reputation: 83.3, mentions_30d: 2, health_status: "COMPLETE", window_days: 90, sov: 5 },
    { competitor_id: "c2", competitor_name: "DLF", rank: 2, reputation: 73.3, mentions_30d: 12, health_status: "COMPLETE", window_days: 90, sov: 9 },
  ];
  const seeded = [
    { entity_id: "c3", name: "Oberoi Realty", rank: 2, context_term: "real estate" },
    { entity_id: "c2", name: "DLF", rank: 1, context_term: "real estate" },
  ];
  it("without a seeded list: one card per benchmark row, in the served order", () => {
    const out = buildCompetitorCards(rows, null, "Godrej Properties");
    expect(out.map(c => c.name)).toEqual(["Lodha", "DLF"]);
    expect(out.every(c => !c.seeded && !c.alsoTracked && !c.placeholder)).toBe(true);
  });
  it("seeded competitors first in seed order; one without a benchmark row is 'Tracked, no coverage yet'; the rest are 'also tracked'", () => {
    const out = buildCompetitorCards(rows, seeded, "Godrej Properties");
    expect(out.map(c => c.name)).toEqual(["DLF", "Oberoi Realty", "Lodha"]);
    expect(out.map(c => c.placeholder)).toEqual([false, true, false]);
    expect(out.map(c => c.alsoTracked)).toEqual([false, false, true]);
    const ph = out[1];
    expect(ph.scoreText).toBe("Tracked, no coverage yet");
    expect(ph.hasScore).toBe(false);
    expect(ph.scoreMeaning).toContain("after the next Run Pipeline");
    expect(out[0].scoreText).toBe("73.3 / 100");
    expect(out[2].scoreText).toBe("Not enough coverage");                                              // 2 mentions < 5: unchanged rule
  });
  it("shows the benchmark window, and for a seeded competitor does not say 'together with the client'", () => {
    expect(notEnoughCoverageMessage("Lodha", "Godrej Properties", 2, 90)).toBe(
      "Not enough coverage: only 2 mentions of Lodha together with Godrej Properties in the last 90 days (fewer than 5), so no score is shown.");
    expect(notEnoughCoverageMessage("Lodha", "Godrej Properties", 2, 90, true)).toBe(
      "Not enough coverage: only 2 mentions of Lodha in the last 90 days (fewer than 5), so no score is shown.");
    expect(notEnoughCoverageMessage("Lodha", "Godrej Properties", 1)).toContain("in the last 30 days");   // old rows
    expect(evidenceCaption(8, "Godrej Properties", 90, true)).toContain("last 90 days (articles about this competitor itself");
    expect(competitorCardView(rows[1], "Godrej Properties").evidence).toBe("Based on 12 mentions in the last 90 days");
  });
  it("a seeded competitor whose row has no evidence and no mention is also 'Tracked, no coverage yet', not 'Not enough coverage'", () => {
    const withEmptyRow = [{ competitor_id: "c3", competitor_name: "Oberoi Realty", rank: 0, reputation: null, mentions_30d: 0, health_status: "INSUFFICIENT_EVIDENCE", window_days: 90 }];
    const out = buildCompetitorCards(withEmptyRow, [{ entity_id: "c3", name: "Oberoi Realty", rank: 1 }], "Godrej Properties");
    expect(out[0].scoreText).toBe("Tracked, no coverage yet");
    expect(out[0].placeholder).toBe(true);
    const oneMention = [{ ...withEmptyRow[0], mentions_30d: 1, health_status: "COMPLETE", reputation: 80, rank: 1 }];
    expect(buildCompetitorCards(oneMention, [{ entity_id: "c3", name: "Oberoi Realty", rank: 1 }], "Godrej Properties")[0].scoreText).toBe("Not enough coverage");
  });
  it("the placeholder is never a score or a zero", () => {
    const v = placeholderCardView("Oberoi Realty", "Godrej Properties");
    expect(v.scoreText).not.toMatch(/\d/);
    expect(v.rankText).toBeNull();
    expect(v.sovText).toBeNull();
  });
});
