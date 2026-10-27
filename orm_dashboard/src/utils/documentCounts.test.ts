import { describe, it, expect } from "vitest";
import { parseDocumentCounts, sentimentSlicesFromCounts, topicSlicesFromCounts, coverageNote } from "@/utils/documentCounts";

const raw = { total_documents: 1603, listed_documents: 500, sentiment: { positive: 343, neutral: 1168, negative: 131, unscored: 8 }, topics: { Legal: 40, Product: 3, General: 1560 } };

describe("document counts (Analytics 500 cap)", () => {
  it("parses a good payload and rejects anything else", () => {
    expect(parseDocumentCounts(raw)!.total_documents).toBe(1603);
    expect(parseDocumentCounts(null)).toBeNull();
    expect(parseDocumentCounts([])).toBeNull();
    expect(parseDocumentCounts({ total_documents: "x" })).toBeNull();
  });
  it("builds the donut slices from the true totals, dropping empty ones", () => {
    expect(sentimentSlicesFromCounts(parseDocumentCounts(raw)!).map(s => [s.name, s.value])).toEqual([["Positive", 343], ["Neutral", 1168], ["Negative", 131]]);
    expect(sentimentSlicesFromCounts(parseDocumentCounts({ ...raw, sentiment: { positive: 0, neutral: 5, negative: 0 } })!).map(s => s.name)).toEqual(["Neutral"]);
  });
  it("topics under the display floor are left out, the rest sorted high to low", () => {
    expect(topicSlicesFromCounts(parseDocumentCounts(raw)!, 5)).toEqual([{ name: "General", value: 1560 }, { name: "Legal", value: 40 }]);
  });
  it("says so when the day-by-day charts see fewer articles than exist", () => {
    expect(coverageNote(parseDocumentCounts(raw), 500)).toBe("Sentiment and topic totals cover all 1,603 articles. Day-by-day charts use the newest 500.");
    expect(coverageNote(parseDocumentCounts({ ...raw, total_documents: 300 }), 300)).toBeNull();
    expect(coverageNote(null, 500)).toBeNull();
  });
});
