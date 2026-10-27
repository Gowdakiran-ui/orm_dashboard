import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import {
  clientRadarValues, competitorRadarValues, buildRadarData, bars, clientShareOfVoice, rankedEntityCount, rankLabel, emptyStateMessage,
  comparedCompetitorsLabel, articleCountLabel, activityScopeNote, evidenceCaption, asOfLabel, competitorCardView, noEvidenceMessage, hiddenTopics, hiddenTopicsNote,
  hasEvidence, RADAR_AXES, isLowEvidence, lowEvidenceTitle, notEnoughCoverageMessage, riskTileLabel, fixed, LOW_EVIDENCE_MENTIONS,
} from "@/utils/competitorCompare";

const GODREJ_BREAKDOWN = { sentiment: 55.564516129032256, risk: 99.36112274821953, source: 96.84, visibility: 11.9 };
const EMAAR = { name: "EMAAR", health_status: "COMPLETE", reputation_score: 93.33466640005332, sentiment_score: 1.0, risk_score: 0.0, share_of_voice: 0.155, rank: 1 };
const M3M = { name: "M3M", health_status: "INSUFFICIENT_EVIDENCE", reputation_score: null, sentiment_score: null, risk_score: null, share_of_voice: null, rank: 0 };

describe("client risk containment (F-01)", () => {
  it("uses the stored risk component as it is: 99.36, not 100 - 99.36", () => {
    const v = clientRadarValues(75.48, GODREJ_BREAKDOWN, 95.19);
    expect(v.riskContainment).toBeCloseTo(99.3611, 3);
    expect(v.riskContainment).not.toBeCloseTo(0.6389, 2);
  });
  it("a competitor's containment is 100 minus its average risk", () => {
    expect(competitorRadarValues({ ...EMAAR, risk_score: 4.7619 })!.riskContainment).toBeCloseTo(95.2381, 3);
  });
});

describe("same score on both sides (F-04)", () => {
  it("the client's reputation point is its comparable score, not the overall score", () => {
    const v = clientRadarValues(75.4848, GODREJ_BREAKDOWN, 95.19);
    expect(v.reputation).toBe(75.4848);
  });
  it("the radar axis is named Comparable Score for both entities", () => {
    expect(RADAR_AXES[0].subject).toBe("Comparable Score");
    const client = clientRadarValues(75.4848, GODREJ_BREAKDOWN, 95.19);
    const { rows } = buildRadarData("Godrej", client, "EMAAR", competitorRadarValues(EMAAR));
    expect(rows[0]).toMatchObject({ subject: "Comparable Score", Godrej: 75.4848, EMAAR: 93.33466640005332 });
  });
  it("competitor sentiment is rescaled (x+1)*50 like the client's 0-100 component", () => {
    expect(competitorRadarValues(EMAAR)!.sentiment).toBe(100);
    expect(competitorRadarValues({ ...EMAAR, sentiment_score: -0.375 })!.sentiment).toBe(31.25);
  });
});

describe("a missing value is never plotted as 0 (F-02, F-10)", () => {
  it("a no-evidence competitor has no radar values and no evidence flag", () => {
    expect(hasEvidence(M3M)).toBe(false);
    expect(competitorRadarValues(M3M)).toBeNull();
    // even if an old payload still carried the placeholder zeros, INSUFFICIENT_EVIDENCE wins
    expect(hasEvidence({ ...M3M, reputation_score: 0, share_of_voice: 0 })).toBe(false);
    expect(competitorRadarValues({ ...M3M, reputation_score: 0 })).toBeNull();
  });
  it("the radar never contains a competitor series for a no-evidence competitor", () => {
    const client = clientRadarValues(75.48, GODREJ_BREAKDOWN, 95.19);
    const r = buildRadarData("Godrej", client, "M3M", competitorRadarValues(M3M));
    expect(r.showCompetitor).toBe(false);
    expect(JSON.stringify(r.rows)).not.toContain('"M3M"');
  });
  it("bars() drops null/undefined values instead of drawing 0", () => {
    expect(bars([{ name: "Godrej", value: null }, { name: "EMAAR", value: 93.3 }])).toEqual([{ name: "EMAAR", value: 93.3 }]);
    expect(bars([{ name: "Godrej", value: undefined }, { name: "M3M", value: null }])).toEqual([]);
    expect(bars([{ name: "x", value: 0 }])).toEqual([{ name: "x", value: 0 }]); // a measured 0 stays 0
  });
  it("a client with no comparable score / breakdown yet is left out, not drawn as 0", () => {
    const empty = clientRadarValues(undefined, null, null);
    expect(empty).toEqual({ reputation: null, sentiment: null, riskContainment: null, sov: null });
    const r = buildRadarData("Godrej", empty, "EMAAR", competitorRadarValues(EMAAR));
    expect(r.showClient).toBe(false);
    expect(r.showCompetitor).toBe(true);
    expect(JSON.stringify(r.rows)).not.toContain('"Godrej"');
  });
  it("client share of voice is null (not 100%) when nothing is compared", () => {
    expect(clientShareOfVoice([])).toBeNull();
    expect(clientShareOfVoice(null)).toBeNull();
    expect(clientShareOfVoice([{ sov: 0.16 }, { sov: 1.6 }])).toBeCloseTo(98.24, 6);
    expect(clientShareOfVoice([{ sov: 80 }, { sov: 40 }])).toBe(0); // floored at 0
  });
});

describe("counts and labels equal what is listed (F-05, F-09)", () => {
  const rows = [
    { competitor_name: "EMAAR", rank: 1, client_rank: 4 }, { competitor_name: "Banke", rank: 2, client_rank: 4 }, { competitor_name: "DLF", rank: 3, client_rank: 4 },
    { competitor_name: "Orris", rank: 5, client_rank: 4 }, { competitor_name: "Lodha", rank: 6, client_rank: 4 },
  ];
  it("ranked entities = ranked competitors + the client", () => {
    expect(rankedEntityCount(rows)).toBe(6);
    expect(rankedEntityCount([])).toBe(0);
    expect(rankedEntityCount([{ rank: 0, client_rank: null }])).toBe(0);
  });
  it("rank label states the denominator and that the client is included", () => {
    expect(rankLabel(5, 6, "Godrej")).toBe("#5 of 6 (includes Godrej)");
    expect(rankLabel(0, 6, "Godrej")).toBe("Unranked");
    expect(rankLabel(null, 6, "Godrej")).toBe("Unranked");
  });
  it("the compared-competitors label uses the number of rows that are actually compared", () => {
    expect(comparedCompetitorsLabel(5, "EMAAR")).toBe("Across all 5 compared competitors -- not just EMAAR");
    expect(comparedCompetitorsLabel(1, null)).toBe("Across all 1 compared competitor -- not just the one selected above");
  });
  it("the empty state never says 'No tracked competitors yet.' when competitors are being compared", () => {
    const names = rows.map(r => r.competitor_name);
    const e = emptyStateMessage({ comparedNames: names, searchStatus: undefined, clientName: "Godrej" })!;
    expect(e.title).not.toContain("No tracked competitors yet");
    expect(e.title).toContain("5 competitors are being compared with Godrej");
    expect(e.detail).toContain("EMAAR, Banke, DLF, Orris, Lodha");
    expect(emptyStateMessage({ comparedNames: [], searchStatus: undefined, clientName: "Godrej" })!.title).toBe("No tracked competitors yet.");
  });
  it("no empty-state card while a search is searching, tracked, or an unpromoted candidate", () => {
    for (const st of ["searching", "tracked", "unpromoted_candidate"]) {
      expect(emptyStateMessage({ comparedNames: [], searchStatus: st, clientName: "Godrej" })).toBeNull();
    }
  });
  it("article count has correct singular/plural and the scope note names the 500-article limit", () => {
    expect(articleCountLabel(1)).toBe("1 article");
    expect(articleCountLabel(0)).toBe("0 articles");
    expect(articleCountLabel(7)).toBe("7 articles");
    expect(activityScopeNote("Godrej")).toContain("newest 500");
  });
});

describe("evidence, dates and hidden topics (F-11, F-12)", () => {
  it("mentions caption is factual and handles singular", () => {
    expect(evidenceCaption(1, "Godrej")).toBe("Based on 1 mention in the last 30 days (only articles that also mention Godrej count).");
    expect(evidenceCaption(10, "Godrej")).toContain("10 mentions");
    expect(evidenceCaption(null, "Godrej")).toBeNull();
  });
  it("as-of label is a date, deterministic in UTC, and null for bad input", () => {
    expect(asOfLabel("2026-10-02T08:46:35.438010+00:00")).toBe("As of 02-10-2026");
    expect(asOfLabel(null)).toBeNull();
    expect(asOfLabel("not a date")).toBeNull();
  });
  it("the no-evidence message names both entities and states why", () => {
    expect(noEvidenceMessage("M3M", "Godrej")).toBe("No qualifying coverage yet: no article found so far mentions both M3M and Godrej, so there is nothing to score.");
  });
  it("topics under the display floor are listed so the bars adding up to under 100% is explained", () => {
    const ents: { total_documents: number; topic_counts: Record<string, number> }[] = [
      { total_documents: 591, topic_counts: { General: 188, "Regulatory Risk": 4, "Customer Satisfaction": 3, "Labor Relations": 1 } },
      { total_documents: 1, topic_counts: { "Regulatory Risk": 1 } },
    ];
    const hidden = hiddenTopics(ents, ["General"]);
    expect(hidden).toEqual(["Customer Satisfaction", "Labor Relations", "Regulatory Risk"]);
    expect(hiddenTopicsNote(hidden)).toContain("3 topics with fewer than 5 articles");
    expect(hiddenTopicsNote([])).toBeNull();
  });
});

describe("minimum evidence for a competitor score and risk label (display only)", () => {
  it("flags fewer than 5 mentions, not 5 or more, and never an unknown count", () => {
    expect(LOW_EVIDENCE_MENTIONS).toBe(5);
    expect(isLowEvidence(1)).toBe(true);
    expect(isLowEvidence(4)).toBe(true);
    expect(isLowEvidence(4.4)).toBe(true);
    expect(isLowEvidence(5)).toBe(false);
    expect(isLowEvidence(11)).toBe(false);
    expect(isLowEvidence(null)).toBe(false);
    expect(isLowEvidence(undefined)).toBe(false);
  });
  it("the live Godrej mention counts flag EMAAR and Banke only", () => {
    const live: Record<string, number> = { EMAAR: 1, "Banke International Properties": 1, DLF: 10, "Orris Infrastructure": 11, Lodha: 8 };
    expect(Object.entries(live).filter(([, n]) => isLowEvidence(n)).map(([k]) => k)).toEqual(["EMAAR", "Banke International Properties"]);
  });
  it("the text states the threshold; a low-evidence competitor has no radar score, a normal one keeps it", () => {
    expect(lowEvidenceTitle()).toContain("Fewer than 5 mentions");
    expect(notEnoughCoverageMessage("Banke", "Godrej", 1)).toBe("Not enough coverage: only 1 mention of Banke together with Godrej in the last 30 days (fewer than 5), so no score is shown.");
    expect(hasEvidence({ health_status: "COMPLETE", reputation_score: 80, mentions_30d: 1 })).toBe(false);
    expect(hasEvidence({ health_status: "COMPLETE", reputation_score: 80, mentions_30d: 5 })).toBe(true);
    expect(hasEvidence({ health_status: "COMPLETE", reputation_score: 80 })).toBe(true);   // unknown count is not hidden
  });
  it("the Risk tile says which coverage it counts", () => {
    expect(riskTileLabel("Godrej Properties")).toBe("Risk in coverage that mentions Godrej Properties");
  });
  it("fixed() never throws on missing values and keeps measured zeros", () => {
    expect(fixed(undefined, 1)).toBe("N/A");
    expect(fixed(null, 2)).toBe("N/A");
    expect(fixed(0, 1)).toBe("0.0");
    expect(fixed(93.33466, 2)).toBe("93.33");
  });
});

describe("removed unused API surface", () => {
  it("fetchShareOfVoice and its route are not referenced anywhere in the frontend source", () => {
    const api = readFileSync(path.resolve(__dirname, "../lib/api.ts"), "utf-8");
    expect(api).not.toContain("fetchShareOfVoice");
    expect(api).not.toContain("/share-of-voice");
    expect(api).not.toContain("competitive-summary");
  });
});

describe("no trend wording on the page (ground rule 2)", () => {
  const strip = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
  const TREND = /\b(trending|trend|improving|declining|steady|stable|this week|rising|falling)\b/i;
  for (const f of ["components/CompetitorsTab.tsx", "utils/competitorCompare.ts"]) {
    it(`${f} has no trend-like words in code or text`, () => {
      const src = strip(readFileSync(path.resolve(__dirname, "..", f), "utf-8"));
      expect(src).not.toMatch(TREND);
    });
  }
  it("the competitor info texts have no trend-like words", () => {
    const src = readFileSync(path.resolve(__dirname, "../lib/metricDefinitions.tsx"), "utf-8");
    const a = src.indexOf("export function CompetitorRadarAxesDefinition");
    const b = src.indexOf("export function TopicOwnershipDefinition");
    expect(src.slice(a, b)).not.toMatch(TREND);
  });
});


describe("competitor cards", () => {
  const row = (over: any) => ({ competitor_id: "1", competitor_name: "Lodha", rank: 1, reputation: 83.3, sov: 1.36, health_status: "COMPLETE", mentions_30d: 6, as_of: "2026-10-20T03:41:10Z", ...over });
  it("a scored competitor gets a plain meaning per number and a dated 'Data as of'", () => {
    const v = competitorCardView(row({}), "Godrej Properties");
    expect(v).toMatchObject({ hasScore: true, scoreText: "83.3 / 100", rankText: "Ranked #1 with Godrej Properties", sovText: "1.4% share of voice", evidence: "Based on 6 mentions in the last 30 days", thin: false, thinNote: null });
    expect(v.scoreMeaning).toContain("that also mention Godrej Properties");
    expect(v.sovMeaning).toContain("about 1 are Lodha");
    expect(v.asOf).toMatch(/^Data as of \d{2}-\d{2}-2026$/);
  });
  it("one mention (Banke: 80 from 1 mention) shows Not enough coverage instead of a score; 5 mentions shows it", () => {
    const v = competitorCardView(row({ competitor_name: "Banke", reputation: 80, mentions_30d: 1 }), "Godrej");
    expect(v.hasScore).toBe(false);
    expect(v.scoreText).toBe("Not enough coverage");
    expect(v.rankText).toBeNull();
    expect(v.scoreMeaning).toContain("only 1 mention of Banke together with Godrej");
    expect(competitorCardView(row({ mentions_30d: 4 }), "Godrej").hasScore).toBe(false);
    expect(competitorCardView(row({ mentions_30d: 5 }), "Godrej").hasScore).toBe(true);
  });
  it("no evidence says what happened instead of a number", () => {
    const v = competitorCardView(row({ competitor_name: "Orris", rank: 0, reputation: null, health_status: "INSUFFICIENT_EVIDENCE", mentions_30d: 0, sov: 0 }), "Godrej");
    expect(v.hasScore).toBe(false);
    expect(v.scoreText).toBe("Not enough coverage");
    expect(v.scoreMeaning).toContain("No article from the last 30 days mentions both Orris and Godrej");
  });
  it("missing as_of / mentions are simply left out", () => {
    const v = competitorCardView(row({ as_of: null, mentions_30d: null }), "Godrej");
    expect(v.asOf).toBeNull();
    expect(v.evidence).toBeNull();
  });
});
