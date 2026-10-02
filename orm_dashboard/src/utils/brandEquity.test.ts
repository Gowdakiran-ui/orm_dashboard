import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "fs";
import path from "path";
import { formatFractionAsPercent } from "./formatPercent";
import {
  riskStatsFromSummary,
  computeExecStats,
  computeCompetitiveStanding,
  computeVerdict,
  pickTopCompetitor,
  sourceState,
  formatAsOf,
} from "./brandEquity";

const bench = (over: any) => ({ competitor_name: "X", rank: 1, sov: 1, client_rank: 4, client_share_of_voice: 95.56, ...over });

describe("riskStatsFromSummary (server-computed document risk)", () => {
  const block = { visible_documents: 646, scored_documents: 624, unscored_documents: 22, total: 22, critical: 0, high: 0, medium: 22, average: 33.7, top: [{ title: "a", risk: 33 }, { title: "b", risk: 33 }] };

  it("maps the server block without recounting anything", () => {
    const s = riskStatsFromSummary(block)!;
    expect(s).toMatchObject({ total: 22, critical: 0, high: 0, medium: 22, dangerCount: 0, dominantLevel: "MEDIUM", unscored: 22 });
    expect(s.avg).toBeCloseTo(33.7);
    expect(s.topRiskDocs.map(t => t.title)).toEqual(["a", "b"]);
  });

  it("different inputs give different outputs", () => {
    expect(riskStatsFromSummary({ ...block, critical: 2, medium: 20 })!.dangerCount).toBe(2);
    expect(riskStatsFromSummary({ ...block, critical: 2, medium: 20 })!.dominantLevel).toBe("CRITICAL");
    expect(riskStatsFromSummary({ ...block, total: 0, medium: 0, average: null, top: [] })!.dominantLevel).toBe("NONE");
  });

  it("a missing or malformed block is unavailable (null), never zeros", () => {
    expect(riskStatsFromSummary(undefined)).toBeNull();
    expect(riskStatsFromSummary(null)).toBeNull();
    expect(riskStatsFromSummary({})).toBeNull();
    expect(riskStatsFromSummary({ ...block, total: "22" })).toBeNull();
  });

  it("zero risky documents keeps a null average (not 0)", () => {
    const s = riskStatsFromSummary({ ...block, total: 0, medium: 0, average: null, top: [] })!;
    expect(s.total).toBe(0);
    expect(s.avg).toBeNull();
  });

  it("keeps at most two top items and ignores malformed ones", () => {
    const s = riskStatsFromSummary({ ...block, top: [{ title: "x", risk: 50 }, { nope: 1 }, { title: "y", risk: 40 }, { title: "z", risk: 30 }] })!;
    expect(s.topRiskDocs.map(t => t.title)).toEqual(["x", "y"]);
  });

  it("an item count of unchecked documents defaults to 0 when absent", () => {
    const { unscored_documents, ...rest } = block;
    expect(riskStatsFromSummary(rest)!.unscored).toBe(0);
  });
});

describe("computeCompetitiveStanding", () => {
  it("uses the engine's own rank and share of voice", () => {
    const s = computeCompetitiveStanding([bench({ competitor_name: "EMAAR", rank: 1 })], false, null);
    expect(s).toMatchObject({ state: "ready", rank: 4, shareOfVoice: 95.56, topCompetitor: "EMAAR" });
  });

  it("zero rows -> empty (never a 100% share of voice)", () => {
    const s = computeCompetitiveStanding([], false, null);
    expect(s.state).toBe("empty");
    expect(s.shareOfVoice).toBeNull();
    expect(s.rank).toBeNull();
  });

  it("fetch error -> error state with no rank or share of voice", () => {
    const s = computeCompetitiveStanding([bench({})], false, "Telemetry Offline");
    expect(s).toMatchObject({ state: "error", rank: null, shareOfVoice: null });
  });

  it("loading -> loading state, never rank #1 or zeros", () => {
    const s = computeCompetitiveStanding([], true, null);
    expect(s).toMatchObject({ state: "loading", rank: null, shareOfVoice: null });
  });

  it("an unranked client stays unranked (null), not 'Not Ranked' text or a guess", () => {
    const s = computeCompetitiveStanding([bench({ client_rank: null })], false, null);
    expect(s.rank).toBeNull();
    expect(s.shareOfVoice).toBe(95.56);
  });

  it("share of voice does not depend on how many rows were returned", () => {
    const one = computeCompetitiveStanding([bench({})], false, null).shareOfVoice;
    const many = computeCompetitiveStanding(Array.from({ length: 40 }, (_, i) => bench({ competitor_name: `C${i}` })), false, null).shareOfVoice;
    expect(many).toBe(one);
  });
});

describe("pickTopCompetitor", () => {
  it("is deterministic: lowest positive rank, ties by name, rank 0 never wins", () => {
    const rows = [
      bench({ competitor_name: "Zed", rank: 1 }),
      bench({ competitor_name: "Alpha", rank: 1 }),
      bench({ competitor_name: "Unranked", rank: 0 }),
      bench({ competitor_name: "Third", rank: 3 }),
    ];
    expect(pickTopCompetitor(rows)?.competitor_name).toBe("Alpha");
    expect(pickTopCompetitor([...rows].reverse())?.competitor_name).toBe("Alpha");
  });

  it("returns null when nothing is ranked", () => {
    expect(pickTopCompetitor([bench({ rank: 0 })])).toBeNull();
    expect(pickTopCompetitor([])).toBeNull();
  });
});

describe("computeVerdict", () => {
  const base = {
    riskState: "ready" as const, advisoryState: "ready" as const, summaryReady: true,
    execAlert: { open: false }, dangerCount: 0, totalRisks: 5, advisory: { flagged: false, lead: "Nothing significant to flag right now." },
  };

  it("healthy client -> green, not the advisory's 'nothing to flag' text in yellow", () => {
    const v = computeVerdict(base);
    expect(v.kind).toBe("clear");
    expect(v.emoji).toBe("🟢");
    expect(v.text).toContain("No Critical or High risks flagged");
  });

  it("advisory flagged -> yellow with its lead", () => {
    const v = computeVerdict({ ...base, advisory: { flagged: true, lead: "High risk currently flagged." } });
    expect(v).toMatchObject({ kind: "flagged", emoji: "🟡", text: "High risk currently flagged." });
  });

  it("Critical/High documents -> flagged count", () => {
    expect(computeVerdict({ ...base, dangerCount: 1 }).text).toBe("1 risk flagged as Critical or High.");
    expect(computeVerdict({ ...base, dangerCount: 3 }).text).toBe("3 risks flagged as Critical or High.");
  });

  it("open executive alert wins", () => {
    const v = computeVerdict({ ...base, execAlert: { open: true, alert: { entity_name: "Jane", severity: "CRITICAL" } }, dangerCount: 2 });
    expect(v).toMatchObject({ kind: "alert", emoji: "🔴" });
    expect(v.text).toContain("Jane");
  });

  it("failed advisory fetch -> unavailable, never green", () => {
    const v = computeVerdict({ ...base, advisoryState: "error", advisory: null });
    expect(v.kind).toBe("unavailable");
    expect(v.emoji).not.toBe("🟢");
  });

  it("failed documents fetch -> unavailable, never 'no risks'", () => {
    expect(computeVerdict({ ...base, riskState: "error" }).kind).toBe("unavailable");
  });

  it("loading -> loading state", () => {
    expect(computeVerdict({ ...base, riskState: "loading" }).kind).toBe("loading");
    expect(computeVerdict({ ...base, advisoryState: "loading" }).kind).toBe("loading");
  });

  it("never states a time window or a stability/trend claim", () => {
    const texts = [
      computeVerdict(base).text,
      computeVerdict({ ...base, dangerCount: 2 }).text,
      computeVerdict({ ...base, execAlert: { open: true, alert: { entity_name: "A", severity: "HIGH" } } }).text,
      computeVerdict({ ...base, advisoryState: "error" }).text,
    ].join(" ").toLowerCase();
    for (const w of ["this week", "stable", "steady", "trending", "improving", "declining"]) expect(texts).not.toContain(w);
  });
});

describe("computeExecStats", () => {
  const execs = [
    { name: "Bee", score: 56.3, document_count: 11 },
    { name: "Ann", score: 58.7, document_count: 1 },
  ];
  it("most mentioned by document_count; highest/lowest by reputation score", () => {
    const s = computeExecStats(execs);
    expect(s.mostMentioned).toBe("Bee");
    expect(s.highest.name).toBe("Ann");
    expect(s.lowest.name).toBe("Bee");
    expect(s.total).toBe(2);
  });
  it("an executive without a numeric score is not read as 0", () => {
    const s = computeExecStats([...execs, { name: "NoScore", score: null, document_count: 2 }]);
    expect(s.lowest.name).toBe("Bee");
    expect(s.total).toBe(3);
  });
  it("empty list -> nothing to name", () => {
    expect(computeExecStats([])).toMatchObject({ total: 0, mostMentioned: null, highest: null, lowest: null });
  });
});

describe("source state + freshness", () => {
  it("loading wins over error; error wins over ready", () => {
    expect(sourceState(true, "boom")).toBe("loading");
    expect(sourceState(false, "boom")).toBe("error");
    expect(sourceState(false, null)).toBe("ready");
    expect(sourceState(undefined, undefined)).toBe("ready");
  });
  it("formatAsOf returns null for missing/invalid input, text for a real date", () => {
    expect(formatAsOf(null)).toBeNull();
    expect(formatAsOf("not-a-date")).toBeNull();
    expect(formatAsOf("2026-10-01T12:39:23Z")).toMatch(/2026/);
  });
});

// Static guard: no trend detection / label / claim anywhere in src/.
// Allow-list: the lucide icon name `TrendingUp` (an icon, not a feature).
function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) walk(full, out);
    else if (/\.(ts|tsx)$/.test(e.name) && !/\.test\.ts$/.test(e.name)) out.push(full);
  }
  return out;
}
const SRC = path.resolve(__dirname, "..");
const stripComments = (t: string) => t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const stripIcons = (t: string) => t.replace(/\bTrendingUp\b/g, "");

describe("trend removal (static guard over all of src/)", () => {
  const files = walk(SRC);
  it("finds the source tree", () => expect(files.length).toBeGreaterThan(20));
  for (const f of files) {
    const rel = path.relative(SRC, f).split(path.sep).join("/");
    it(`${rel} has no trend field, label or claim in code or strings`, () => {
      const code = stripIcons(stripComments(readFileSync(f, "utf-8")));
      expect(code).not.toMatch(/trending|trendDisplay|trendEvents|trend-events|IMPROVING|DECLINING|\bsteady\b|this week/i);
      expect(code).not.toMatch(/\btrends?\b/i);
      expect(code).not.toMatch(/trend_|\.trend\b|\btrend:/i);
    });
  }
  it("chart and tab names say history, not trend", () => {
    const all = files.map(f => stripIcons(stripComments(readFileSync(f, "utf-8")))).join("\n");
    expect(all).not.toMatch(/Reputation & Sentiment Trends|Reputation Trend|Sentiment Trend|Average Sentiment Over Time/);
  });
});

describe("plain wording on the Brand Equity card", () => {
  const card = readFileSync(path.resolve(SRC, "components/ReputationSummaryCard.tsx"), "utf-8");
  it("has no internals or jargon in the main text", () => {
    for (const w of ["latest 500", "entity–document", "entity-document", "readings", "scored=false"]) {
      expect(card).not.toContain(w);
    }
  });
});

describe("formatFractionAsPercent (confidence / coverage)", () => {
  it("null, undefined, NaN and strings are unknown, never 0% or NaN%", () => {
    for (const v of [null, undefined, NaN, "0.5", {}]) expect(formatFractionAsPercent(v as any)).toBe("Unknown");
  });
  it("real fractions format as whole percents (0 is a real 0%)", () => {
    expect(formatFractionAsPercent(0.914)).toBe("91%");
    expect(formatFractionAsPercent(0)).toBe("0%");
    expect(formatFractionAsPercent(1)).toBe("100%");
  });
});
