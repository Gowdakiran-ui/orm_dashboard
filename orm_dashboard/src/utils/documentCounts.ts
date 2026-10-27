// True totals from /documents/client/{id}/counts (every visible document), used by the Analytics Overview so its
// headline numbers are not limited to the newest 500 articles the list endpoint returns. Pure helpers, no React.

export interface DocumentCounts {
  total_documents: number;
  listed_documents: number;
  sentiment: { positive: number; neutral: number; negative: number; unscored?: number };
  topics: Record<string, number>;
}

const n = (x: unknown): number => (typeof x === "number" && Number.isFinite(x) ? x : 0);

/** Accepts only a well-formed payload; anything else (an older API, an error) is null and the page keeps its list-based numbers. */
export function parseDocumentCounts(raw: any): DocumentCounts | null {
  if (!raw || typeof raw !== "object" || typeof raw.total_documents !== "number" || !raw.sentiment || typeof raw.topics !== "object") return null;
  return {
    total_documents: n(raw.total_documents),
    listed_documents: n(raw.listed_documents),
    sentiment: { positive: n(raw.sentiment.positive), neutral: n(raw.sentiment.neutral), negative: n(raw.sentiment.negative), unscored: n(raw.sentiment.unscored) },
    topics: raw.topics || {},
  };
}

export function sentimentSlicesFromCounts(c: DocumentCounts) {
  return [
    { name: "Positive", value: c.sentiment.positive, color: "#10B981" },
    { name: "Neutral", value: c.sentiment.neutral, color: "#64748B" },
    { name: "Negative", value: c.sentiment.negative, color: "#EF4444" },
  ].filter(item => item.value > 0);
}

export function topicSlicesFromCounts(c: DocumentCounts, minCount: number) {
  return Object.entries(c.topics)
    .map(([name, value]) => ({ name, value: n(value) }))
    .filter(item => item.value >= minCount)
    .sort((a, b) => b.value - a.value);
}

/** One plain sentence when the page only draws part of the corpus in its day-by-day charts; null when nothing is hidden. */
export function coverageNote(c: DocumentCounts | null, listedLength: number): string | null {
  if (!c || c.total_documents <= listedLength) return null;
  return `Sentiment and topic totals cover all ${c.total_documents.toLocaleString("en-IN")} articles. Day-by-day charts use the newest ${listedLength.toLocaleString("en-IN")}.`;
}
