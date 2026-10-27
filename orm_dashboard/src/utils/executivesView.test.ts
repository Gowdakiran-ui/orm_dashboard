import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { executiveView, basedOnLine, eventsLabel, appearsInLine, isStale, ageInDays } from "./executivesView";

const NOW = new Date("2026-10-03T12:00:00Z").getTime();
const scored = { score: 57.97767, grade: "D", document_count: 11, health_status: "PARTIAL", as_of: "2026-10-02T08:33:56Z" };

describe("executiveView", () => {
  it("shows a real score and grade with at least 3 documents", () => {
    const v = executiveView(scored, NOW);
    expect(v).toMatchObject({ badge: "scored", scoreText: "57.98", gradeText: "D", hasScore: true, staleNote: null });
  });
  it("withholds the letter grade under 3 documents (display only)", () => {
    const v = executiveView({ ...scored, score: 60.192, grade: "C", document_count: 1 }, NOW);
    expect(v.badge).toBe("low_evidence");
    expect(v.scoreText).toBe("60.19");
    expect(v.gradeText).toBe("Grade withheld: fewer than 3 documents");
    expect(v.gradeText).not.toContain("C");
  });
  it("an unscored person never gets a number or a grade", () => {
    for (const e of [
      { score: null, grade: null, health_status: "NO_SCORE_YET" },
      { score: 0, grade: "NA", health_status: "INSUFFICIENT_EVIDENCE", document_count: 0 },
      undefined,
    ]) {
      const v = executiveView(e as any, NOW);
      expect(v).toMatchObject({ badge: "no_score", scoreText: "No score yet", gradeText: "-", hasScore: false });
    }
  });
  it("marks rows last scored more than 14 days ago as stale, with the date", () => {
    const v = executiveView({ ...scored, as_of: "2026-09-12T12:59:55Z" }, NOW);
    expect(v.staleNote).toMatch(/^Stale: last scored /);
    expect(isStale("2026-09-19T12:00:00Z", NOW)).toBe(false); // exactly 14 days
    expect(isStale("2026-09-18T11:00:00Z", NOW)).toBe(true);
    expect(ageInDays(null, NOW)).toBeNull();
  });
});

describe("sentences", () => {
  it("states the document count and the biggest drag, not 'weak visibility'", () => {
    const line = basedOnLine({ ...scored, biggest_drag: { label: "Sentiment", points_lost: 21.4 } })!;
    expect(line).toBe("Based on 11 documents. Biggest drag on the score: Sentiment (21.4 points lost).");
    expect(basedOnLine({ document_count: 1 })).toBe("Based on 1 document.");
    expect(basedOnLine({})).toBeNull();
  });
  it("event count label equals the document count it is given", () => {
    expect(eventsLabel(8)).toBe("8 documents behind this score");
    expect(eventsLabel(1)).toBe("1 document behind this score");
  });
  it("never implies the person works for the client", () => {
    expect(appearsInLine("Adani Group")).toContain("Appears in Adani Group coverage");
    expect(appearsInLine("Adani Group")).toContain("does not mean they work for");
  });
});

describe("Executives page source", () => {
  const src = readFileSync(path.join(__dirname, "..", "components", "ExecutivesTab.tsx"), "utf8");
  it("has no free-text path that creates anything and no list of people: no polling, no promote-all, no browser name matching, no tracked/candidate lists", () => {
    for (const w of ["MAX_SEARCH_POLLS", "pollExecutiveSearch", "setTimeout", "onPromoteExecutives", "promoteExecutiveCandidates", "Executive Figure", "extracted_entities",
                     "fetchReviewedExecutiveCandidates", "Tracked Executives", "Candidates Found", "were hidden", "trackedRows"]) {
      expect(src).not.toContain(w);
    }
  });
  it("adds only through the one-candidate endpoint, after a confirmation step", () => {
    expect(src).toContain("addExecutiveCandidate(clientId, person.id)");
    expect(src).toContain("Confirm add");
  });
});


import { pickTopTrackedExecutives, trackedCardView } from "./executivesView";

describe("default tracked-executive cards", () => {
  const rows = [
    { name: "NoCov", score: 0, health_status: "INSUFFICIENT_EVIDENCE", document_count: 0 },
    { name: "Low", score: 40, grade: "D", health_status: "COMPLETE", document_count: 9 },
    { name: "High", score: 70, grade: "B", health_status: "COMPLETE", document_count: 3 },
  ];
  it("scored people first by score; unscored last; capped", () => {
    expect(pickTopTrackedExecutives(rows).map(r => r.name)).toEqual(["High", "Low", "NoCov"]);
    expect(pickTopTrackedExecutives(rows, 2).map(r => r.name)).toEqual(["High", "Low"]);
    expect(pickTopTrackedExecutives(null)).toEqual([]);
  });
  it("a person with older coverage says so; one with none says that; old payloads keep the plain line", () => {
    const gaurav = { name: "Gaurav Pandey", score: 0, health_status: "INSUFFICIENT_EVIDENCE", document_count: 0, articles_all_time: 9, latest_article_at: "2025-08-04T00:00:00Z" };
    expect(trackedCardView(gaurav, "Godrej Properties").detail).toBe("9 articles mention this person with Godrej Properties, but none in the last 30 days (newest 04-08-2025), so there is no score yet.");
    expect(trackedCardView({ ...gaurav, articles_all_time: 1 }, "Godrej").detail).toContain("1 article mentions this person with Godrej");
    expect(trackedCardView({ ...gaurav, articles_all_time: 0 }, "Godrej").detail).toBe("No article mentions this person together with Godrej, so there is nothing to score.");
    expect(trackedCardView({ name: "X", score: 0, health_status: "INSUFFICIENT_EVIDENCE" }, "Godrej").detail).toContain("last 30 days");
  });
  it("cards say what happened", () => {
    expect(trackedCardView(rows[0], "Acme").headline).toBe("No score yet");
    expect(trackedCardView(rows[0], "Acme").detail).toContain("No coverage mentioning Acme");
    expect(trackedCardView(rows[2], "Acme")).toMatchObject({ hasScore: true, headline: "70.00 · grade B", detail: "3 articles in the last 30 days" });
    expect(trackedCardView({ ...rows[2], document_count: 2 }, "Acme").headline).toContain("grade withheld");
  });
});
