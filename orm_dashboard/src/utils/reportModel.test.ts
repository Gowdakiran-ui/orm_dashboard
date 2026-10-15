import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { ReputationSummaryCard } from "@/components/ReputationSummaryCard";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/d", useSearchParams: () => new URLSearchParams() }));
import { buildReportModel, reportFileName, reportIsAllUnavailable, exportDisabledReason, SENTIMENT_CUTOFF, MIN_TOPIC_ARTICLES, UNAVAILABLE_SECTION, MAX_FLAGGED_ROWS, POSITIVE_MENTIONS_NOTE, POSITIVE_SHARE_NOTE, readingGuide, type ReportInput, type ReportModel, type Block } from "./reportModel";
import { stripEmoji, formatIST, formatISTDate, istDateKey, needsShaping } from "./reportText";
import { calculateSentimentDistribution } from "./calculateSentimentDistribution";
import { buildRiskHeatmap } from "./riskHeatmap";

// Fixtures live in reportTestFixtures.ts (shared with the renderer and summary tests).
import { mkDocs, analyticsFor, summary, alerts, hist, input } from "./reportTestFixtures";

const allBlocks = (m: ReportModel) => m.sections.flatMap(s => s.blocks);
const text = (m: ReportModel) => JSON.stringify(m);
const section = (m: ReportModel, id: string) => m.sections.find(s => s.id === id)!;
const tables = (blocks: Block[]) => blocks.filter((b): b is Extract<Block, { type: "table" }> => b.type === "table");
const cellText = (c: any) => (typeof c === "string" ? c : c.text);

describe("report model, full data", () => {
  const m = buildReportModel(input());
  it("has the three pages in order and a cover", () => {
    expect(m.sections.map(s => s.title)).toEqual(["Brand Equity", "Risk Center", "Executive Analytics"]);
    expect(m.meta.title).toBe("XOOP | Reputation Report");
    expect(m.meta.clientName).toBe("Acme Corp");
    expect(m.meta.userEmail).toBe("me@example.com");
    expect(m.meta.dataWindow[0]).toContain("newest 140 of 140");
    expect(m.meta.dataWindow.join(" ")).toContain("Reputation score as of 2 Oct 2026, 8:32 PM IST");
    expect(m.meta.dataWindow.join(" ")).toContain("Risk scores as of 3 Oct 2026, 11:25 AM IST");
  });
  it("Brand Equity: score, grade, sentences, people, standing, alert line", () => {
    const t = JSON.stringify(section(m, "brand-equity"));
    expect(t).toContain("75.51");
    expect(t).toContain("Grade B · as of 2 Oct 2026, 8:32 PM IST");
    expect(t).toContain("Acme Corp's reputation score is 75.51 (B), as of 2 Oct 2026, 8:32 PM IST.");
    expect(t).toContain("98 positive / 418 neutral / 49 negative");
    expect(t).toContain("Jane Doe has the highest reputation score among them (80.0)");
    expect(t).toContain("Acme Corp ranks #2 among the competitors found in coverage.");
    expect(t).toContain("No open executive-risk alerts.");
  });
  it("Risk Center: five tiles from the server counts, alerts with their AI text, matrix and flagged table", () => {
    const rc = section(m, "risk-center").blocks;
    const stats = rc.find(b => b.type === "stats") as any;
    expect(stats.items.map((i: any) => [i.label, i.value])).toEqual([
      ["Flagged Articles", "14"], ["Critical", "2"], ["High", "3"], ["Medium", "9"], ["Highest Score", "80.3"],
    ]);
    const al = rc.filter((b): b is Extract<Block, { type: "alert" }> => b.type === "alert");
    expect(al).toHaveLength(2);
    expect(al[0].alert).toMatchObject({ severity: "HIGH", title: "Company: Multi-Signal Incident: Acme", what: "2 risk signals.", when: "Oct 08, 2026 11:14 UTC", nextStep: "Review the documents." });
    expect(al[0].alert.raised).toBe("8 Oct 2026, 4:44 PM IST");
    expect(al[1].alert).toMatchObject({ what: null, nextStep: null, title: "Executive: Exec" });
    const [matrix, flagged] = tables(rc);
    expect(matrix.rows).toHaveLength(3);
    expect(flagged.landscape).toBe(true);
    expect(flagged.columns).toEqual(["Headline", "Score", "Severity", "Source", "Date (IST)", "Sentiment", "Topic"]);
    // same ordering as the screen: highest score first
    const scores = flagged.rows.map(r => parseFloat(cellText(r[1])));
    expect([...scores].sort((a, b) => b - a)).toEqual(scores);
  });
  it("Executive Analytics: both subtabs, KPIs, chart blocks, heatmap table and its footnote", () => {
    const ea = section(m, "executive-analytics").blocks;
    const heads = ea.filter(b => b.type === "heading").map((b: any) => b.text);
    expect(heads).toContain("Reputation & Sentiment History");
    expect(heads).toContain("Risk & Alert Profile");
    expect(heads).not.toContain("Average Sentiment History");
    expect(ea.filter(b => b.type === "chart").map((b: any) => b.id).sort()).toEqual(["alerts", "repHistory", "sentiment", "topics"]);
    expect(JSON.stringify(ea)).toContain("Articles that have not been risk-scored are not counted in the heatmap. Topics with fewer than 5 articles are not shown.");
    const heat = tables(ea).find(t => t.columns[0] === "Topic category")!;
    expect(heat.landscape).toBe(true);
    expect(cellText(heat.rows[heat.rows.length - 1][0])).toBe("COLUMN TOTALS");
  });
  it("labels the two different 'positive' numbers so they cannot be confused", () => {
    const t = text(m);
    expect(t).toContain("Positive mentions (brand-gated)");
    expect(t).toContain("Positive share (document sentiment)");
    expect(t).not.toContain('"Positive Mentions"');
    expect(t).not.toContain('"Positive Share"');
  });
  it("notes: window, IST, browser time zone for chart days, scoring change", () => {
    const n = m.notes.map(x => x.text).join(" ");
    expect(n).toContain("newest 500 articles at most");
    expect(n).toContain("IST (Asia/Kolkata)");
    expect(n).toContain("Chart day labels use the time zone Asia/Calcutta.");
    expect(n).toContain("Scoring method updated 1 Oct 2026");
  });
  it("the two positive measures are explained once, in the notes, not under the tiles", () => {
    expect(m.notes.map(x => x.id)).toEqual(expect.arrayContaining(["positiveMentions", "positiveShare"]));
    expect(m.notes.find(x => x.id === "positiveMentions")!.text).toBe(POSITIVE_MENTIONS_NOTE);
    expect(m.notes.find(x => x.id === "positiveShare")!.text).toBe(POSITIVE_SHARE_NOTE);
    expect(JSON.stringify(m.sections)).not.toContain("labelled Positive by the sentiment model");
    expect(m.notes.map(x => x.term)).toEqual(expect.arrayContaining(["Positive mentions (brand-gated)", "Positive share (document sentiment)"]));
  });
  it("never carries original_content or alertSeverityData", () => {
    expect(text(m)).not.toContain("SECRET-ARTICLE-BODY");
    expect(text(m)).not.toContain("original_content");
    expect(text(m)).not.toContain("alertSeverityData");
  });
  it("is plain JSON (serialisable)", () => {
    expect(JSON.parse(JSON.stringify(m))).toEqual(m);
  });
});

describe("no-data rule: N/A, never a fake zero", () => {
  it("Positive share and Topics Covered are N/A with no data; the screen would say 0% and 0", () => {
    const m = buildReportModel(input({ documents: [], analytics: analyticsFor([], [], []) }));
    const stats = section(m, "executive-analytics").blocks.find(b => b.type === "stats") as any;
    const by = Object.fromEntries(stats.items.map((i: any) => [i.label, i.value]));
    expect(by["Positive share (document sentiment)"]).toBe("N/A");
    expect(by["Topics Covered"]).toBe("N/A");
    expect(by["Sentiment Score"]).toBe("N/A");
  });
  it("Current Reputation and Brand Equity score are N/A for no_data / insufficient_evidence", () => {
    for (const status of ["no_data", "insufficient_evidence"]) {
      const m = buildReportModel(input({ reputationSummary: summary({ reputation: { score: null, grade: null, status, computed_at: null } }) }));
      const ea = section(m, "executive-analytics").blocks.find(b => b.type === "stats") as any;
      expect(ea.items[0].value).toBe("N/A");
      const be = section(m, "brand-equity").blocks.find(b => b.type === "stats") as any;
      expect(be.items[0].value).toBe("N/A");
    }
  });
  it("a real score of 0 is not hidden as N/A", () => {
    const m = buildReportModel(input({ reputationSummary: summary({ reputation: { score: 0, grade: "F", status: "ok", computed_at: "2026-10-02T15:02:27Z" } }) }));
    const be = section(m, "brand-equity").blocks.find(b => b.type === "stats") as any;
    expect(be.items[0].value).toBe("0.00");
  });
});

describe("failed sources are reported, not dropped", () => {
  it("summary failed: Brand Equity says Unavailable, other pages still render", () => {
    const m = buildReportModel(input({ reputationSummary: null, reputationSummaryError: "Telemetry Offline" }));
    expect(section(m, "brand-equity").blocks).toEqual([{ type: "text", text: UNAVAILABLE_SECTION, style: "muted" }]);
    expect(section(m, "risk-center").blocks.length).toBeGreaterThan(3);
    expect(section(m, "executive-analytics").blocks.length).toBeGreaterThan(3);
  });
  it("documents failed: matrix, flagged table and analytics sections say Unavailable and keep their headings", () => {
    const m = buildReportModel(input({ documents: [], documentsError: "Telemetry Offline", analytics: analyticsFor([], alerts, hist) }));
    const rc = section(m, "risk-center").blocks;
    const i = rc.findIndex(b => b.type === "heading" && (b as any).text.startsWith("Risk Matrix"));
    expect(rc[i + 1]).toMatchObject({ type: "text", text: UNAVAILABLE_SECTION });
    const ea = JSON.stringify(section(m, "executive-analytics"));
    expect(ea).toContain("Reputation & Sentiment History");
    expect(ea).toContain(UNAVAILABLE_SECTION);
  });
  it("alerts failed, executives failed, benchmarks failed", () => {
    const m = buildReportModel(input({ alertsError: "x", executivesError: "y", benchmarksError: "z" }));
    expect(JSON.stringify(section(m, "risk-center"))).toContain(UNAVAILABLE_SECTION);
    const be = JSON.stringify(section(m, "brand-equity"));
    expect(be.split(UNAVAILABLE_SECTION).length - 1).toBe(2);
    expect(JSON.stringify(section(m, "executive-analytics"))).toContain(UNAVAILABLE_SECTION);
  });
});

describe("empty sections say so", () => {
  const docs = mkDocs(60, () => ({ risk: 0, scored: true, risk_exact: 0, risk_level: "LOW" }));
  const m = buildReportModel(input({ alerts: [], documents: docs, analytics: analyticsFor(docs, [], hist), reputationSummary: summary({ document_risk: { visible_documents: 60, total: 0, critical: 0, high: 0, medium: 0, average: null, highest: null, as_of: null, top: [], unscored_documents: 0 } }) }));
  it("no alerts: a sentence, no chart", () => {
    const rc = section(m, "risk-center").blocks;
    expect(rc).toContainEqual({ type: "text", text: "No unacknowledged alerts." });
    const ea = section(m, "executive-analytics").blocks;
    expect(ea.some(b => b.type === "chart" && b.id === "alerts")).toBe(false);
    expect(JSON.stringify(ea)).toContain("No open alerts. Nothing unacknowledged for this client.");
  });
  it("no flagged articles", () => {
    expect(section(m, "risk-center").blocks).toContainEqual({ type: "text", text: "No flagged articles." });
  });
});

describe("benchmark sentinel and no competitors", () => {
  it("handles the 'No competitor intelligence available.' row if it ever reaches the model, and an empty list", () => {
    for (const benchmarks of [[{ message: "No competitor intelligence available." }], []]) {
      const m = buildReportModel(input({ benchmarks }));
      expect(JSON.stringify(section(m, "brand-equity"))).toContain("No competitor comparison available yet.");
    }
  });
});

describe("emoji", () => {
  it("stripEmoji removes pictographs, flags, ZWJ sequences and keycaps, and keeps ordinary text", () => {
    expect(stripEmoji("The Case that Shook Adani😱")).toBe("The Case that Shook Adani");
    expect(stripEmoji("💰 Top-Paid Executives — 2026 📊")).toBe("Top-Paid Executives — 2026");
    expect(stripEmoji("a 👨‍👩‍👧 b 🇮🇳 c 1️⃣ d")).toBe("a b c 1 d");
    expect(stripEmoji("₹349 cr, 22% — “quoted” é")).toBe("₹349 cr, 22% — “quoted” é");
    expect(stripEmoji(null)).toBe("");
  });
  it("the model has no emoji in titles, sentences or alert text", () => {
    const docs = mkDocs(60, (i) => (i % 9 === 0 ? { title: `Flagged ${i} 😱🔥` } : {}));
    const m = buildReportModel(input({
      documents: docs, analytics: analyticsFor(docs, alerts, hist),
      alerts: [{ ...alerts[0], title: "Alert 🚨", ai_summary: { what: "what 🔴", when: "now", how_to_solve: "fix ✅" } }],
    }));
    expect(text(m)).not.toMatch(/\p{Extended_Pictographic}/u);
    expect(text(m)).toContain("Flagged 0");
  });
  it("needsShaping flags complex scripts, not Latin/₹/curly quotes", () => {
    expect(needsShaping("तीन साल बाद")).toBe(true);
    expect(needsShaping("ரூ.6 லட்சம்")).toBe(true);
    expect(needsShaping("Godrej ₹349 cr — “ok” é ß")).toBe(false);
    expect(needsShaping("Привет Ελληνικά")).toBe(false);
  });
});

describe("IST", () => {
  it("formats in Asia/Kolkata with the zone shown, across the UTC/IST midnight", () => {
    expect(formatIST("2026-10-01T20:00:00Z")).toBe("2 Oct 2026, 1:30 AM IST");
    expect(formatIST("2026-10-01T18:29:00Z")).toBe("1 Oct 2026, 11:59 PM IST");
    expect(formatIST("2026-10-02T15:02:27Z")).toBe("2 Oct 2026, 8:32 PM IST");
    expect(formatISTDate("2026-10-01T20:00:00Z")).toBe("2 Oct 2026 IST");
    expect(istDateKey("2026-10-01T20:00:00Z")).toBe("2026-10-02");
    expect(istDateKey("2026-10-01T18:29:00Z")).toBe("2026-10-01");
    expect(formatIST(null)).toBeNull();
    expect(formatIST("not a date")).toBeNull();
  });
  it("the file name uses the IST date and a sanitised client name", () => {
    expect(reportFileName("Godrej Properties", new Date("2026-10-01T20:00:00Z"))).toBe("XOOP_Godrej_Properties_Reputation_Report_2026-10-02.pdf");
    expect(reportFileName("Acme/Corp: <Ltd>.", new Date("2026-10-01T10:00:00Z"))).toBe("XOOP_Acme_Corp_Ltd_Reputation_Report_2026-10-01.pdf");
    expect(reportFileName("", new Date("2026-10-01T10:00:00Z"))).toBe("XOOP_client_Reputation_Report_2026-10-01.pdf");
  });
  it("cover and flagged dates are IST, not the machine's zone", () => {
    const m = buildReportModel(input({ generatedAt: new Date("2026-10-01T20:00:00Z") }));
    expect(m.meta.generatedAt).toBe("2 Oct 2026, 1:30 AM IST");
    expect(m.meta.fileName).toContain("2026-10-02");
    const flagged = tables(section(m, "risk-center").blocks)[1];
    expect(flagged.rows.every(r => /IST/.test(cellText(r[4])))).toBe(true);
  });
});

describe("Brand Equity: stat labels match the page", () => {
  it("every stat label except the relabelled positive-mentions one is printed on the page itself", async () => {
    const i = input();
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(React.createElement(ThemeProvider, { children: React.createElement(ReputationSummaryCard, {
        reputationSummaryLoading: false, reputationSummaryError: null, reputationSummary: i.reputationSummary, planAdvisory: i.planAdvisory,
        executives: i.executives, activeClientName: i.clientName, normalizedBenchmarks: i.benchmarks,
      }) }));
    });
    const page = host.textContent!.toLowerCase();
    const stats = section(buildReportModel(i), "brand-equity").blocks.find(b => b.type === "stats") as any;
    for (const it of stats.items) {
      if (it.label.startsWith("Positive mentions")) { expect(page).toContain("positive mentions"); continue; }
      expect(page).toContain(it.label.toLowerCase());
    }
    await act(async () => root.unmount());
    host.remove();
  });
});

describe("large inputs", () => {
  it("lists up to 500 flagged articles in the table and says when more exist", () => {
    const many = mkDocs(1300, () => ({ risk: 40, risk_exact: 40.2, scored: true, risk_level: "MEDIUM" }));
    const m = buildReportModel(input({ documents: many, analytics: analyticsFor(many, [], hist) }));
    const flagged = tables(section(m, "risk-center").blocks)[1];
    expect(flagged.rows).toHaveLength(MAX_FLAGGED_ROWS);
    expect(JSON.stringify(section(m, "risk-center"))).toContain(`Listing the first ${MAX_FLAGGED_ROWS} of 1300 flagged articles.`);
  });
  it("all rows of an ordinary list are kept", () => {
    const m = buildReportModel(input());
    const flagged = tables(section(m, "risk-center").blocks)[1];
    expect(flagged.rows.length).toBeGreaterThan(10);
    expect(allBlocks(m).length).toBeGreaterThan(20);
  });
});

// ---- fixes after the pre-commit forensics (F1, F2, F5, F8, clarity items) -----------------------------
const strings = (v: unknown, out: string[] = []): string[] => {
  if (typeof v === "string") out.push(v);
  else if (Array.isArray(v)) v.forEach(x => strings(x, out));
  else if (v && typeof v === "object") Object.values(v).forEach(x => strings(x, out));
  return out;
};
const statValues = (blocks: Block[]) => Object.fromEntries(blocks.filter((b): b is Extract<Block, { type: "stats" }> => b.type === "stats").flatMap(b => b.items.map(i => [i.label, i.value])));

describe("F1: a client with nothing risk-scored is not reported as 'all clear'", () => {
  const empty = { visible_documents: 0, scored_documents: 0, unscored_documents: 0, total: 0, critical: 0, high: 0, medium: 0, average: null, highest: null, as_of: null, top: [] };
  const unscored = { ...empty, visible_documents: 80, unscored_documents: 80 };
  for (const [label, document_risk] of [["empty client", empty], ["every article unscored", unscored]] as const) {
    it(`${label}: verdict is 'Not enough data yet' and the risk counts print N/A, not 0`, () => {
      const docs = label === "empty client" ? [] : mkDocs(80, () => ({ scored: false, risk: 0, risk_exact: null, risk_level: null, risk_sentiment: null }));
      const m = buildReportModel(input({ documents: docs, alerts: [], analytics: analyticsFor(docs, [], []), repHistory: [], reputationSummary: summary({ document_risk }) }));
      const be = section(m, "brand-equity").blocks;
      expect(be[0]).toMatchObject({ type: "text", text: "Not enough data yet" });
      const beStats = statValues(be);
      expect(beStats["Risk Signals"]).toBe("N/A");
      expect(beStats["Total Risks Tracked (all time)"]).toBe("N/A");
      expect(JSON.stringify(be)).not.toContain("No Critical or High");
      expect(JSON.stringify(be)).not.toContain("0 tracked risks");
      expect(JSON.stringify(be)).not.toContain("No items of coverage carry a risk above Low");
      expect(JSON.stringify(be)).toContain("No articles have been risk-scored yet");
      const rc = statValues(section(m, "risk-center").blocks);
      expect(rc).toEqual({ "Flagged Articles": "N/A", Critical: "N/A", High: "N/A", Medium: "N/A", "Highest Score": "N/A" });
      expect(statValues(section(m, "executive-analytics").blocks)["Critical-Risk Documents"]).toBe("N/A");
    });
  }
  it("a scored client with nothing above Low keeps real zeros and the all-clear sentence", () => {
    const docs = mkDocs(60, () => ({ risk: 0, scored: true, risk_exact: 0, risk_level: "LOW" }));
    const m = buildReportModel(input({ documents: docs, analytics: analyticsFor(docs, [], hist), reputationSummary: summary({ document_risk: { ...empty, visible_documents: 60, scored_documents: 60 } }) }));
    expect(section(m, "brand-equity").blocks[0]).toMatchObject({ text: "No Critical or High risks flagged. Watching 0 tracked risks." });
    expect(statValues(section(m, "risk-center").blocks)["Flagged Articles"]).toBe("0");
    expect(statValues(section(m, "brand-equity").blocks)["Risk Signals"]).toBe("0");
  });
  it("a summary that does not send scored_documents (older payload) is not treated as 'nothing scored'", () => {
    const m = buildReportModel(input({ reputationSummary: summary({ document_risk: { ...empty, visible_documents: 60, scored_documents: undefined } }) }));
    expect(statValues(section(m, "risk-center").blocks)["Flagged Articles"]).toBe("0");
  });
});

describe("F2: when the report would be nothing but 'Unavailable'", () => {
  it("reportIsAllUnavailable is true only when the summary, the articles and the alerts all failed", () => {
    const base = { reputationSummary: summary(), reputationSummaryError: null, documentsError: null, alertsError: null };
    expect(reportIsAllUnavailable(base)).toBe(false);
    expect(reportIsAllUnavailable({ ...base, reputationSummary: null, reputationSummaryError: "x", documentsError: "x", alertsError: "x" })).toBe(true);
    expect(reportIsAllUnavailable({ ...base, reputationSummary: null, documentsError: "x", alertsError: "x" })).toBe(true);
    expect(reportIsAllUnavailable({ ...base, reputationSummaryError: "x", documentsError: "x" })).toBe(false);
    expect(reportIsAllUnavailable({ ...base, reputationSummaryError: "x", alertsError: "x" })).toBe(false);
    expect(reportIsAllUnavailable({ ...base, documentsError: "x", alertsError: "x" })).toBe(false);
  });
  it("in exactly that state every content block of the model is the Unavailable line (the check and the model cannot drift)", () => {
    const failed = input({ reputationSummary: null, reputationSummaryError: "x", documentsError: "x", alertsError: "x", documents: [], alerts: [], repHistory: [], analytics: analyticsFor([], [], []) });
    expect(reportIsAllUnavailable(failed)).toBe(true);
    const m = buildReportModel(failed);
    const content = allBlocks(m).filter(b => b.type !== "heading");
    expect(content.length).toBeGreaterThan(0);
    for (const b of content) expect(b).toMatchObject({ type: "text", text: UNAVAILABLE_SECTION });
  });
  it("exportDisabledReason: pipeline running and all-failed disable the button with their own tooltip; zero data does not", () => {
    const ok = { hasClient: true, pipelineRunning: false, loading: false, allUnavailable: false };
    expect(exportDisabledReason(ok)).toBeUndefined();
    expect(exportDisabledReason({ ...ok, hasClient: false })).toBe("Select a company first");
    expect(exportDisabledReason({ ...ok, pipelineRunning: true })).toBe("Report available when the pipeline finishes");
    expect(exportDisabledReason({ ...ok, loading: true })).toBe("Waiting for the dashboard data to finish loading");
    expect(exportDisabledReason({ ...ok, allUnavailable: true })).toBe("Data couldn't be loaded. Refresh and try again.");
    // the pipeline reason wins over "loading": the data reloads right after a run finishes
    expect(exportDisabledReason({ ...ok, pipelineRunning: true, loading: true })).toBe("Report available when the pipeline finishes");
  });
  it("the dashboard page passes the SELECTED client's pipeline state to that function (static guard)", () => {
    const page = readFileSync(path.resolve(__dirname, "../app/dashboard/page.tsx"), "utf-8");
    expect(page).toContain("pipelineRunning: pipeline.pipelineRunning");
    expect(page).toMatch(/usePipelineManager\(data\.clientId,/);
    expect(page).toContain("disabled={exportDisabledReason !== undefined}");
  });
  it("a client with zero data and no failures is still exportable", () => {
    const m = buildReportModel(input({ documents: [], alerts: [], analytics: analyticsFor([], [], []), repHistory: [], reputationSummary: summary({ document_risk: { visible_documents: 0, scored_documents: 0, unscored_documents: 0, total: 0, critical: 0, high: 0, medium: 0, average: null, highest: null, as_of: null, top: [] } }) }));
    expect(reportIsAllUnavailable(input({ documents: [] }))).toBe(false);
    expect(m.sections).toHaveLength(3);
  });
});

describe("F5: file names", () => {
  const when = new Date("2026-10-01T10:00:00Z");
  const base = (n: string) => reportFileName(n, when).replace(/^XOOP_/, "").replace(/_Reputation_Report_2026-10-01\.pdf$/, "");
  it("keeps letters, combining marks and numbers of any script", () => {
    expect(base("अदाणी एंटरप्राइजेज")).toBe("अदाणी_एंटरप्राइजेज");
    expect(base("தமிழ் நிறுவனம் 2026")).toBe("தமிழ்_நிறுவனம்_2026");
    expect(base("Café Zoë")).toBe("Café_Zoë");
  });
  it("replaces / \\ : * ? \" < > | and every other symbol with one underscore", () => {
    expect(base('A/B\\C:D*E?F"G<H>I|J')).toBe("A_B_C_D_E_F_G_H_I_J");
    expect(base("A  --  B.&C")).toBe("A_B_C");
  });
  it("removes emoji and trims leading and trailing spaces and symbols", () => {
    expect(base("Rocket 🚀 Co ✨")).toBe("Rocket_Co");
    expect(base("   Padded Name   ")).toBe("Padded_Name");
    expect(base("__x__")).toBe("x");
  });
  it("caps the client part at 60 characters (code points, not bytes) without leaving a trailing underscore", () => {
    const long = "A".repeat(150);
    expect(base(long)).toBe("A".repeat(60));
    expect(Array.from(base("अ".repeat(150)))).toHaveLength(60);
    expect(base("𝒜".repeat(100))).toBe("𝒜".repeat(60));
    expect(base("abcde ".repeat(30)).endsWith("_")).toBe(false);
    expect(Array.from(base("ab ".repeat(40))).length).toBeLessThanOrEqual(60);
  });
  it("falls back to 'client' when nothing is left, and adds no collision suffix", () => {
    expect(base("")).toBe("client");
    expect(base("🚀🚀 /// ***")).toBe("client");
    expect(reportFileName("Acme: Corp", when)).toBe(reportFileName("Acme/ Corp", when));
  });
});

describe("F8: malformed numbers never reach the report", () => {
  const badDocs = mkDocs(60, i => (i === 0 ? { risk: NaN, risk_exact: Infinity } : {}));
  const a = analyticsFor(badDocs, alerts, hist);
  const bad = input({
    reputationSummary: summary({
      reputation: { score: NaN, grade: "B", status: "ok", computed_at: "2026-10-02T15:02:27Z" },
      document_risk: { visible_documents: 140, scored_documents: 135, unscored_documents: 5, total: -3, critical: NaN, high: 3, medium: 9, average: Infinity, highest: 250, as_of: null, top: [{ title: "Bad", risk: NaN }, { title: "Worse", risk: -4 }] },
      sentiment: { positive: NaN, neutral: -1, negative: 49, dominant: "neutral" },
    }),
    executives: [{ name: "Jane Doe", score: NaN, document_count: -2 }, { name: "Bob Roe", score: 150, document_count: 1.5 }],
    benchmarks: [{ competitor_name: "Rival", rank: NaN, client_rank: Infinity, client_share_of_voice: -5 }],
    repHistory: [{ rawDate: "2026-09-20T00:00:00Z", date: "Sep 20", score: NaN }, { rawDate: "2026-10-02T15:02:00Z", date: "Oct 2", score: 130 }, ...hist],
    documents: badDocs,
    analytics: {
      ...a,
      sentimentDistData: [{ name: "Positive", value: NaN }, { name: "Neutral", value: -2 }],
      topicDistData: [{ name: "General", value: Infinity }],
      alertTimelineData: [{ date: "Oct 8", count: NaN }],
      riskHeatmapData: { categories: ["General"], severities: ["LOW", "MEDIUM", "HIGH", "CRITICAL"], grid: { General: { LOW: { count: 3, avgRisk: NaN, avgSentiment: Infinity }, MEDIUM: { count: 2, avgRisk: 40, avgSentiment: 0.1 }, HIGH: { count: 0 }, CRITICAL: { count: 0 } } } },
    },
  });
  const m = buildReportModel(bad);
  it("no NaN, Infinity, undefined or [object Object] anywhere in the model", () => {
    for (const s of strings(m)) expect(s).not.toMatch(/NaN|Infinity|undefined|\[object|\bnull\b/);
  });
  it("Brand Equity: score, risk counts, sentiment counts and the sentences built from them", () => {
    const be = section(m, "brand-equity").blocks;
    const v = statValues(be);
    expect(v["Reputation Score"]).toBe("N/A");
    expect(v["Risk Signals"]).toBe("N/A");
    expect(v["Total Risks Tracked (all time)"]).toBe("N/A");
    expect(v["Positive mentions (brand-gated)"]).toBe("N/A");
    expect(v["Overall Tone"]).toBe("N/A");
    expect(JSON.stringify(be)).toContain("Sentiment counts: N/A.");
    expect(JSON.stringify(be)).toContain("Risk figures are unavailable.");
    expect(JSON.stringify(be)).not.toContain("highest reputation score");
  });
  it("Risk Center tiles and the flagged table", () => {
    const rc = section(m, "risk-center").blocks;
    expect(statValues(rc)).toEqual({ "Flagged Articles": "N/A", Critical: "N/A", High: "N/A", Medium: "N/A", "Highest Score": "N/A" });
    const flagged = tables(rc)[1];
    expect(flagged.rows.every(r => /^[0-9.]+$|^N\/A$/.test(cellText(r[1])))).toBe(true);
  });
  it("Executive Analytics: KPIs, chart tables, history, alert stats and heatmap cells", () => {
    const ea = section(m, "executive-analytics").blocks;
    const v = statValues(ea);
    expect(v["Current Reputation"]).toBe("N/A");
    expect(v["Positive share (document sentiment)"]).toBe("N/A");
    expect(v["Sentiment Score"]).toBe("N/A");
    expect(v["Critical-Risk Documents"]).toBe("N/A");
    expect(v["Alert Status"]).toBe("N/A");
    const t = tables(ea);
    expect(t.find(x => x.columns[0] === "Sentiment")!.rows.map(r => cellText(r[1]))).toEqual(["N/A", "N/A"]);
    expect(t.find(x => x.columns[0] === "Topic")!.rows.map(r => cellText(r[1]))).toEqual(["N/A"]);
    const history = t.find(x => x.columns[0] === "Scored at (IST)")!;
    expect(history.rows.slice(0, 2).map(r => cellText(r[1]))).toEqual(["N/A", "N/A"]);
    expect(JSON.stringify(ea)).toContain("Avg (N/A) · Peak: N/A");
  });
  it("heatmap: a bad average prints N/A in that cell; a bad count turns the whole heatmap into N/A", () => {
    const ea = JSON.stringify(section(m, "executive-analytics"));
    expect(ea).toContain("Risk Score: N/A");
    expect(ea).toContain("Sentiment: N/A");
    const worse = buildReportModel(input({ analytics: { ...a, riskHeatmapData: { categories: ["General"], severities: ["LOW"], grid: { General: { LOW: { count: NaN } } } } } }));
    expect(JSON.stringify(section(worse, "executive-analytics"))).toContain("N/A (the heatmap counts could not be read).");
  });
  it("executives and competitor figures with unusable numbers are left out of the sentences", () => {
    const be = JSON.stringify(section(m, "brand-equity"));
    expect(be).not.toMatch(/#NaN|#Infinity/);
    expect(be).toContain("could not be ranked against competitors yet");
  });
  it("valid values on the boundary are still printed (0 and 100 are real scores, 0 is a real count)", () => {
    const ok = buildReportModel(input({ reputationSummary: summary({ reputation: { score: 100, grade: "A+", status: "ok", computed_at: null } }) }));
    expect(statValues(section(ok, "brand-equity").blocks)["Reputation Score"]).toBe("100.00");
    const zero = buildReportModel(input({ reputationSummary: summary({ reputation: { score: 0, grade: "F", status: "ok", computed_at: null } }) }));
    expect(statValues(section(zero, "brand-equity").blocks)["Reputation Score"]).toBe("0.00");
  });
});

describe("clarity: reading guide and chart captions", () => {
  const m = buildReportModel(input());
  const guideList = readingGuide();
  it("the reading guide wording covers every term the report prints, and only those", () => {
    expect(guideList.map(g => g.term)).toEqual(["N/A", "Unavailable", "Risk levels", "Flagged article", "Confidence", "Listed Feed", "Newest 500 articles", "Times"]);
    const printed = strings(m.sections).join("\n") + m.notes.map(n => n.text).join("\n");
    for (const term of ["N/A", "Unavailable", "Confidence", "Listed Feed"]) expect(printed + JSON.stringify(m.meta)).toContain(term);
    // "evidence score" is a dashboard term the report never prints, so it is not explained.
    expect(printed).not.toMatch(/evidence score/i);
    expect(guideList.map(g => g.text).join(" ")).not.toMatch(/evidence score/i);
  });
  it("the reused definitions still say the same thing on the dashboard (lib/metricDefinitions.tsx)", () => {
    const defs = readFileSync(path.resolve(__dirname, "../lib/metricDefinitions.tsx"), "utf-8").replace(/\s+/g, " ");
    const guide = Object.fromEntries(guideList.map(g => [g.term, g.text]));
    for (const phrase of ["routine coverage, no action needed", "worth monitoring", "warrants review", "needs immediate attention"]) {
      expect(defs).toContain(phrase); expect(guide["Risk levels"]).toContain(phrase);
    }
    for (const phrase of ["how sure the system is about the signals it scored the article on (its tone and subject), from 0 to 100, shown as Low (under 33), Medium (33–66) or High (67+). It is not a prediction that the risk will happen or recur."]) {
      expect(defs).toContain(phrase); expect(guide["Confidence"].replace(/^H/, "h")).toContain(phrase);
    }
    for (const phrase of ["Each article counts once, even when several outlets report the same story, and articles of any age are included."]) {
      expect(defs).toContain(phrase); expect(guide["Flagged article"]).toContain(phrase);
    }
    for (const phrase of ["across the articles listed on this page", "including articles that scored 0 risk"]) expect(defs).toContain(phrase);
    expect(guide["Listed Feed"]).toContain("including articles that scored 0 risk");
  });
  it("the risk bands in the guide are the platform's 25/50/75", () => {
    expect(guideList.find(g => g.term === "Risk levels")!.text).toContain("Low (0–25)");
    expect(guideList.find(g => g.term === "Risk levels")!.text).toContain("Critical (76–100)");
  });
  it("every chart has a caption, and the numbers in them are the ones the code uses", () => {
    const charts = allBlocks(m).filter((b): b is Extract<Block, { type: "chart" }> => b.type === "chart");
    expect(charts.map(c => c.id).sort()).toEqual(["alerts", "repHistory", "sentiment", "topics"]);
    for (const c of charts) expect(c.caption.length).toBeGreaterThan(40);
    const cap = Object.fromEntries(charts.map(c => [c.id, c.caption]));
    // sentiment cut-offs: the very function the chart uses
    expect(cap.sentiment).toContain(`above +${SENTIMENT_CUTOFF}`);
    expect(cap.sentiment).toContain(`below -${SENTIMENT_CUTOFF}`);
    const dist = (s: number) => calculateSentimentDistribution([{ sentiment: s }]);
    expect(dist(SENTIMENT_CUTOFF)).toEqual({ positive: 0, neutral: 1, negative: 0 });
    expect(dist(SENTIMENT_CUTOFF + 0.01)).toEqual({ positive: 1, neutral: 0, negative: 0 });
    expect(dist(-SENTIMENT_CUTOFF)).toEqual({ positive: 0, neutral: 1, negative: 0 });
    expect(dist(-SENTIMENT_CUTOFF - 0.01)).toEqual({ positive: 0, neutral: 0, negative: 1 });
    // topic floor: the constant in useAnalytics.ts
    expect(cap.topics).toContain(`fewer than ${MIN_TOPIC_ARTICLES} articles`);
    expect(readFileSync(path.resolve(__dirname, "../hooks/useAnalytics.ts"), "utf-8")).toContain(`const MIN_TOPIC_DOCUMENT_COUNT = ${MIN_TOPIC_ARTICLES};`);
    // window
    for (const id of ["sentiment", "topics"]) expect(cap[id]).toContain("the newest 140 loaded, 500 at most");
    // the model carries the same captions for the native charts
    expect(m.data.captions).toEqual(cap);
  });
});
