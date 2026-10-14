// The data behind the exported PDF report: a plain, serialisable model built from a snapshot of what the
// dashboard has loaded. No React, no network, no clock (the caller passes `generatedAt`).
//
// Every figure and sentence comes from the same functions the pages use (brandEquity.ts, riskCenter.ts,
// analyticsPanels.ts, riskHeatmap via useAnalytics), so the report cannot drift from the screen. The only
// differences are deliberate: times in IST, emoji removed, "N/A" where the screen would show a bare zero,
// and the footnotes. `original_content` and `alertSeverityData` are never read here.

import { buildBrandEquityView, riskStatsFromSummary, UNAVAILABLE_TEXT, type ReputationSummaryLike } from "@/utils/brandEquity";
import {
  flaggedDocs, buildMatrix, windowNote, unscoredNote, tilesFromSummary, formatScore,
  MATRIX_BANDS, MATRIX_CONFIDENCE, ALERT_ENTITY_TYPE_LABEL,
} from "@/utils/riskCenter";
import {
  overviewKpiValues, formatSentimentScoreKpi, scoringMethodChange, SCORING_CHANGE_NOTE,
  riskPanelFacts, alertTimelineStats, heatmapTotals,
} from "@/utils/analyticsPanels";
import { stripEmoji, formatIST, istDateKey } from "@/utils/reportText";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";

export const UNAVAILABLE_SECTION = "Unavailable (data could not be loaded)";
// The dashboard loads at most this many articles (api.ts fetchDocuments / documents.py hard ceiling).
export const ARTICLE_WINDOW = 500;
export const MAX_FLAGGED_ROWS = 500;

export type ChartId = "sentiment" | "topics" | "repHistory" | "alerts";

export type Cell = string | { text: string; fill?: string; color?: string; bold?: boolean; align?: "left" | "center" | "right" };

export interface ReportAlert {
  severity: string;
  title: string;
  alertType: string;
  raised: string;
  what: string | null;
  when: string | null;
  nextStep: string | null;
}

export type Block =
  | { type: "heading"; level: 2 | 3; text: string }
  | { type: "text"; text: string; style?: "normal" | "muted" | "note" | "bold" }
  | { type: "stats"; items: { label: string; value: string; sub?: string }[] }
  | { type: "table"; columns: string[]; rows: Cell[][]; widths?: number[]; landscape?: boolean; compact?: boolean }
  | { type: "alert"; alert: ReportAlert }
  | { type: "chart"; id: ChartId; title: string; caption: string };

export interface ReportSection { id: string; title: string; blocks: Block[] }

export interface ReportModel {
  meta: {
    title: string;
    clientName: string;
    generatedAt: string;
    userEmail: string | null;
    dataWindow: string[];
    // "How to read this report": the terms the report prints, in plain words (shown on the cover).
    guide: { term: string; text: string }[];
    fileName: string;
  };
  sections: ReportSection[];
  footnotes: string[];
}

export interface ReportInput {
  clientId: string | null;
  clientName: string;
  generatedAt: Date;
  userEmail: string | null;
  // Time zone the chart day labels were bucketed in (useAnalytics uses the browser's).
  browserTimeZone: string;
  reputationSummary: any;
  reputationSummaryError: string | null;
  planAdvisory: any;
  planAdvisoryError: string | null;
  executives: any[];
  executivesError: string | null;
  benchmarks: any[];
  benchmarksError: string | null;
  documents: any[];
  documentsError: string | null;
  alerts: any[];
  alertsError: string | null;
  repHistory: any[];
  historyError: string | null;
  analytics: {
    sentimentDistData: any[];
    topicDistData: any[];
    riskMatrixData: any[];
    riskHeatmapData: any;
    alertTimelineData: any[];
  };
}

const NA = "N/A";
const HEAD_FILL = "#E5E7EB";
const SEVERITY_FILL: Record<string, string> = { CRITICAL: "#FCA5A5", HIGH: "#FDBA74", MEDIUM: "#FDE68A", LOW: "#BBF7D0" };
const HEATMAP_RGB: Record<string, [number, number, number]> = { CRITICAL: [239, 68, 68], HIGH: [249, 115, 22], MEDIUM: [234, 179, 8], LOW: [16, 185, 129] };

// The screen tints a heatmap cell with the severity colour at alpha min(0.12 + 0.15 * count, 0.85); on paper
// that is the same colour blended onto white.
function heatmapFill(sev: string, count: number): string | undefined {
  if (count <= 0) return undefined;
  const a = Math.min(0.12 + count * 0.15, 0.85);
  const [r, g, b] = HEATMAP_RGB[sev];
  const mix = (c: number) => Math.round(255 * (1 - a) + c * a).toString(16).padStart(2, "0");
  return `#${mix(r)}${mix(g)}${mix(b)}`;
}

// Same count-based tint as the screen's matrix cells, as flat paper colours.
function matrixFill(count: number): { fill: string; color?: string } {
  if (count === 0) return { fill: "#F3F4F6" };
  if (count <= 2) return { fill: "#FEE2E2" };
  if (count <= 5) return { fill: "#FCA5A5" };
  return { fill: "#DC2626", color: "#FFFFFF" };
}

const clean = (s: string | null | undefined) => stripEmoji(s);

// ---- Number safety (report only) -------------------------------------------------------------------
// The screen prints whatever number it is given. On paper a malformed value (NaN, Infinity, a negative count, a score
// outside its scale) must never be printed as if it were real, so every number the report prints goes through one of
// these and falls back to "N/A".
const inRange = (v: unknown, lo: number, hi: number): v is number => typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi;
export const isCount = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;
export const isScore100 = (v: unknown): v is number => inRange(v, 0, 100);
export const isUnitScore = (v: unknown): v is number => inRange(v, -1, 1);
const cnt = (v: unknown) => (isCount(v) ? String(v) : NA);

const RISK_COUNT_KEYS = ["total", "critical", "high", "medium"] as const;
const OTHER_COUNT_KEYS = ["visible_documents", "scored_documents", "unscored_documents"] as const;

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => !!v && typeof v === "object";

// A copy of /reputation-summary with unusable numbers removed before the shared page logic reads it, so none of them
// can reach a sentence. `riskBad` = the risk block is there but a count in it is unusable (printed as N/A, as opposed to
// a missing block, which is "Unavailable"); `sentimentBad` = a sentiment count is unusable.
function cleanSummary(rs: unknown): { summary: ReputationSummaryLike | null | undefined; riskBad: boolean; sentimentBad: boolean } {
  if (!isRec(rs)) return { summary: rs as null | undefined, riskBad: false, sentimentBad: false };
  const out: Rec = { ...rs };
  if (isRec(rs.reputation)) {
    out.reputation = { ...rs.reputation, score: isScore100(rs.reputation.score) ? rs.reputation.score : null };
  }
  let riskBad = false;
  if (isRec(rs.document_risk)) {
    const d: Rec = { ...rs.document_risk };
    for (const k of [...RISK_COUNT_KEYS, ...OTHER_COUNT_KEYS]) {
      if (k in d && !isCount(d[k])) {
        delete d[k];
        if ((RISK_COUNT_KEYS as readonly string[]).includes(k)) riskBad = true;
      }
    }
    if (d.average != null && !isScore100(d.average)) d.average = null;
    if (d.highest != null && !isScore100(d.highest)) d.highest = null;
    if (Array.isArray(d.top)) d.top = d.top.filter(t => isRec(t) && isScore100(t.risk));
    out.document_risk = d;
  }
  const s = rs.sentiment;
  const sentimentBad = isRec(s) && !(isCount(s.positive) && isCount(s.neutral) && isCount(s.negative));
  return { summary: out as ReputationSummaryLike, riskBad, sentimentBad };
}

const cleanExecutives = (list: unknown[]): unknown[] =>
  (list || []).map(e => (isRec(e)
    ? { ...e, score: isScore100(e.score) ? e.score : null, document_count: isCount(e.document_count) ? e.document_count : null }
    : e));

const cleanBenchmarks = (list: unknown[]): unknown[] =>
  (list || []).map(b => (isRec(b)
    ? {
        ...b,
        rank: isCount(b.rank) ? b.rank : 0,
        client_rank: isCount(b.client_rank) && b.client_rank > 0 ? b.client_rank : null,
        client_share_of_voice: isScore100(b.client_share_of_voice) ? b.client_share_of_voice : null,
      }
    : b));

// ---- When there is nothing to report ---------------------------------------------------------------
const summaryUnusable = (i: Pick<ReportInput, "reputationSummary" | "reputationSummaryError">) => !!i.reputationSummaryError || !i.reputationSummary;

// True when every part of the report would read "Unavailable": the summary, the articles and the alerts all failed to
// load (the articles feed both Executive Analytics sub-pages; the summary feeds Brand Equity and the Risk Center tiles).
// The Export Report button is disabled in that state: a PDF made of nothing but "Unavailable" is not a report.
export function reportIsAllUnavailable(i: Pick<ReportInput, "reputationSummary" | "reputationSummaryError" | "documentsError" | "alertsError">): boolean {
  return summaryUnusable(i) && !!i.documentsError && !!i.alertsError;
}

// Why the Export Report button is disabled, or undefined when it is not. The order is the order of what the person can do
// about it: pick a company, wait for the pipeline (its data is being rebuilt, so a report would mix old and new figures),
// wait for loading, or refresh after a failure.
export function exportDisabledReason(s: { hasClient: boolean; pipelineRunning: boolean; loading: boolean; allUnavailable: boolean }): string | undefined {
  if (!s.hasClient) return "Select a company first";
  if (s.pipelineRunning) return "Report available when the pipeline finishes";
  if (s.loading) return "Waiting for the dashboard data to finish loading";
  if (s.allUnavailable) return "Data couldn't be loaded. Refresh and try again.";
  return undefined;
}

// ---- "How to read this report" and chart captions ----------------------------------------------------
const { LOW_TO_MEDIUM: LOW_MAX, MEDIUM_TO_HIGH: MED_MAX, HIGH_TO_CRITICAL: HIGH_MAX } = RISK_THRESHOLDS;

// Wording is taken from the dashboard's own explainers (lib/metricDefinitions.tsx: Risk Severity, Flagged articles,
// Risk Matrix, Average Risk Score) so a term reads the same on screen and on paper; reportModel.test.ts checks the shared
// phrases are still in that file. Entries marked "new" have no dashboard equivalent.
export function readingGuide(): { term: string; text: string }[] {
  return [
    // new
    { term: "N/A", text: "There is not enough data to give a figure yet, or the stored value could not be used. It never means zero." },
    // new
    { term: "Unavailable", text: "The data for that part could not be loaded when the report was made. Refresh the dashboard and export again." },
    // Risk Severity
    { term: "Risk levels", text: `Each article's Risk Score (0–100) is placed in a band: Low (0–${LOW_MAX}), routine coverage, no action needed; Medium (${LOW_MAX + 1}–${MED_MAX}), worth monitoring; High (${MED_MAX + 1}–${HIGH_MAX}), warrants review; Critical (${HIGH_MAX + 1}–100), needs immediate attention.` },
    // Flagged articles
    { term: "Flagged article", text: `A collected article whose risk score is above ${LOW_MAX} (Medium severity or higher). Each article counts once, even when several outlets report the same story, and articles of any age are included.` },
    // Risk Matrix
    { term: "Confidence", text: "How sure the system is about the signals it scored the article on (its tone and subject), from 0 to 100, shown as Low (under 33), Medium (33–66) or High (67+). It is not a prediction that the risk will happen or recur." },
    // Average Risk Score (feed)
    { term: "Listed Feed", text: "The Avg Risk Score (Listed Feed) is the mean Risk Score (0–100) across the articles listed in this report (the newest ones, up to 500), including articles that scored 0 risk. Risk Center shows the average of flagged articles only." },
    // new
    { term: "Newest 500 articles", text: `Charts, matrices, the heatmap and the flagged-articles table use the newest ${ARTICLE_WINDOW} articles at most. The count tiles (for example Flagged Articles and Documents Analyzed) cover every article.` },
    // new
    { term: "Times", text: "All times are in IST (Asia/Kolkata), except the day labels on charts, which use the time zone of the browser that made the report, and the alert 'When' text, which is printed as the system recorded it." },
  ];
}

// One caption per chart. Every number in them is the constant the code that draws the chart uses (the +/-0.3 sentiment
// cut-offs: calculateSentimentDistribution.ts; the 5-article topic floor: useAnalytics.ts MIN_TOPIC_DOCUMENT_COUNT).
export const SENTIMENT_CUTOFF = 0.3;
export const MIN_TOPIC_ARTICLES = 5;
function chartCaptions(loadedArticles: number): Record<ChartId, string> {
  const scope = `the newest ${loadedArticles} loaded, ${ARTICLE_WINDOW} at most`;
  return {
    sentiment: `Articles by sentiment score (${scope}): Positive above +${SENTIMENT_CUTOFF}, Negative below -${SENTIMENT_CUTOFF}, Neutral in between. Exact counts are in the table below.`,
    topics: `Articles per topic (${scope}); topics with fewer than ${MIN_TOPIC_ARTICLES} articles are not shown. Exact counts are in the table below.`,
    repHistory: "Each point is one stored Reputation Score (0–100) on the day it was computed (day labels use the browser time zone). Every score with its IST time is in the table below.",
    alerts: "Open (unacknowledged) alerts per day, grouped by the day each was raised, all severities (day labels use the browser time zone). Average and peak are printed below the chart.",
  };
}

// Longest client-name part of the file name, counted in characters (code points), not bytes.
export const FILE_NAME_CLIENT_MAX = 60;

// Letters, combining marks (the vowel signs of Devanagari, Tamil, ...) and numbers of any script are kept; everything
// else (spaces, / \ : * ? " < > |, emoji, punctuation) becomes "_", runs of "_" collapse to one and the ends are trimmed.
export function reportFileName(clientName: string, when: Date): string {
  const squeezed = clean(clientName).replace(/[^\p{L}\p{M}\p{N}]+/gu, "_").replace(/^_+|_+$/g, "");
  const safe = Array.from(squeezed).slice(0, FILE_NAME_CLIENT_MAX).join("").replace(/_+$/g, "") || "client";
  return `XOOP_${safe}_Reputation_Report_${istDateKey(when) ?? "date"}.pdf`;
}

export function buildReportModel(i: ReportInput): ReportModel {
  const name = clean(i.clientName);
  const sections: ReportSection[] = [];
  const footnotes: string[] = [];
  const unavailable = (): Block => ({ type: "text", text: UNAVAILABLE_SECTION, style: "muted" });
  const captions = chartCaptions(i.documents.length);

  const summaryFailed = summaryUnusable(i);
  // Unusable numbers are taken out here, once, so no shared page sentence can print them.
  const { summary, riskBad, sentimentBad } = cleanSummary(i.reputationSummary);
  const executives = cleanExecutives(i.executives);
  const benchmarks = cleanBenchmarks(i.benchmarks);
  const docRisk = summaryFailed ? null : summary?.document_risk;
  const facts = riskPanelFacts({
    riskMatrixData: i.analytics.riskMatrixData,
    reputationSummary: summary,
    reputationSummaryLoading: false,
    reputationSummaryError: i.reputationSummaryError,
    alertTimelineData: i.analytics.alertTimelineData,
  });

  // ---------------------------------------------------------------- Brand Equity
  const be: Block[] = [];
  let riskNA = false;
  if (summaryFailed) {
    be.push(unavailable());
  } else {
    const v = buildBrandEquityView({
      reputationSummary: summary,
      planAdvisory: i.planAdvisory,
      planAdvisoryLoading: false,
      planAdvisoryError: i.planAdvisoryError,
      executives,
      executivesLoading: false,
      executivesError: i.executivesError,
      activeClientName: name,
      normalizedBenchmarks: benchmarks,
      benchmarksLoading: false,
      benchmarksError: i.benchmarksError,
      formatDate: formatIST,
    });
    const rs = v.riskStats;
    // Nothing risk-scored yet (or the counts are unusable): the screen would show 0, the report says N/A.
    riskNA = riskBad || rs?.scored === 0;
    const risk = (n: number | undefined) => (riskNA ? NA : rs && n !== undefined ? String(n) : UNAVAILABLE_TEXT);
    be.push({ type: "text", text: clean(v.verdict.text), style: "bold" });
    be.push({ type: "heading", level: 3, text: "At a glance" });
    be.push({
      type: "stats",
      items: [
        { label: "Reputation Score", value: v.scoreDisplay, sub: v.scoreKnown ? `Grade ${v.gradeDisplay}${v.asOf ? ` · as of ${v.asOf}` : ""}` : v.scoreStatusText },
        { label: "Risk Signals", value: risk(rs?.dangerCount), sub: "Critical + High" },
        {
          label: "Total Risks Tracked (all time)", value: risk(rs?.total),
          sub: riskNA ? (rs?.scored === 0 ? "No risk-scored articles yet" : "Risk figures could not be read") : rs ? `${rs.critical} Critical · ${rs.high} High · ${rs.medium} Medium` : "Risk data unavailable",
        },
        { label: "Positive mentions (brand-gated)", value: sentimentBad ? NA : cnt(v.sentiment.positive), sub: "in coverage" },
        { label: "Overall Tone", value: sentimentBad ? NA : v.sentiment.dominant ?? NA, sub: sentimentBad ? "Sentiment counts could not be read" : `${cnt(v.sentiment.positive)} positive / ${cnt(v.sentiment.neutral)} neutral / ${cnt(v.sentiment.negative)} negative` },
      ],
    });
    be.push({
      type: "text", style: "muted",
      text: "Positive mentions (brand-gated): one mention is one appearance of the client's brand, a product or a tracked person in one piece of coverage, labelled Positive by the sentiment model. Only coverage that also mentions the client's own brand or product counts, and competitors are left out. It is not an article count, so it does not match the Positive share (document sentiment) in Executive Analytics.",
    });
    be.push({ type: "heading", level: 3, text: "Overview" });
    be.push({ type: "text", text: clean(v.overviewText) });
    be.push({ type: "heading", level: 3, text: "Risk Profile" });
    be.push({
      type: "text",
      text: rs?.scored === 0
        ? `No articles have been risk-scored yet, so the risk figures are ${NA}.${v.uncheckedText}`
        : clean(v.riskProfile.kind === "some" ? `${v.riskProfile.before}${v.riskProfile.avg}${v.riskProfile.after}` : v.riskProfile.text),
    });
    be.push({ type: "heading", level: 3, text: "Sentiment" });
    be.push({ type: "text", text: sentimentBad ? `Sentiment counts: ${NA}.` : clean(v.sentimentText) });
    be.push({ type: "heading", level: 3, text: "Notable People in Coverage" });
    be.push({ type: "text", text: v.execState === "error" ? UNAVAILABLE_SECTION : clean(v.peopleText) });
    be.push({ type: "heading", level: 3, text: "Competitive Standing" });
    be.push({ type: "text", text: v.standing.state === "error" ? UNAVAILABLE_SECTION : clean(v.standingText) });
    be.push({ type: "heading", level: 3, text: "Alerts" });
    be.push({ type: "text", text: clean(v.alertLine) });
  }
  sections.push({ id: "brand-equity", title: "Brand Equity", blocks: be });

  // ---------------------------------------------------------------- Risk Center
  const rc: Block[] = [];
  const riskStats = summaryFailed ? null : riskStatsFromSummary(docRisk);
  const tiles = tilesFromSummary(riskStats);
  const tilesNA = !summaryFailed && (riskBad || riskStats?.scored === 0);
  const asOfText = tiles?.asOf ? formatIST(tiles.asOf) : null;
  rc.push({ type: "heading", level: 3, text: `At a glance · all-time counts${asOfText ? ` · scores as of ${asOfText}` : ""}` });
  if (tilesNA) {
    // The screen's tiles show 0 here; on paper nothing was scored, so there is no count to give.
    rc.push({ type: "stats", items: ["Flagged Articles", "Critical", "High", "Medium", "Highest Score"].map(label => ({ label, value: NA })) });
    const nc = unscoredNote(tiles?.unscored);
    if (nc) rc.push({ type: "text", text: nc, style: "note" });
  } else if (!tiles) {
    rc.push(unavailable());
  } else {
    const tv = (n: number | null | undefined) => (n !== null && n !== undefined ? String(n) : UNAVAILABLE_TEXT);
    rc.push({
      type: "stats",
      items: [
        { label: "Flagged Articles", value: tv(tiles.flagged) },
        { label: "Critical", value: tv(tiles.critical) },
        { label: "High", value: tv(tiles.high) },
        { label: "Medium", value: tv(tiles.medium) },
        { label: "Highest Score", value: tiles.highest !== null ? formatScore(tiles.highest) : UNAVAILABLE_TEXT },
      ],
    });
    const nc = unscoredNote(tiles.unscored);
    if (nc) rc.push({ type: "text", text: nc, style: "note" });
  }

  rc.push({ type: "heading", level: 3, text: "Active Alerts" });
  if (i.alertsError) {
    rc.push(unavailable());
  } else if (i.alerts.length === 0) {
    rc.push({ type: "text", text: "No unacknowledged alerts." });
  } else {
    rc.push({ type: "text", text: `${i.alerts.length} Active`, style: "muted" });
    for (const a of i.alerts) {
      const ai = a.ai_summary;
      const typeLabel = ALERT_ENTITY_TYPE_LABEL[a.entity_type];
      rc.push({
        type: "alert",
        alert: {
          severity: clean(a.severity),
          title: `${typeLabel ? `${typeLabel}: ` : ""}${clean(a.title)}`,
          alertType: clean(a.alert_type),
          raised: formatIST(a.created_at) ?? NA,
          what: ai ? clean(ai.what) : null,
          when: ai ? clean(ai.when) || "Unknown" : null,
          nextStep: ai ? clean(ai.how_to_solve) : null,
        },
      });
    }
  }

  const riskDocs = flaggedDocs(i.documents);
  rc.push({ type: "heading", level: 3, text: "Risk Matrix (Severity × Confidence)" });
  if (i.documentsError) {
    rc.push(unavailable());
  } else {
    const matrix = buildMatrix(riskDocs);
    rc.push({
      type: "table",
      columns: ["Severity", "LOW CONFIDENCE", "MED CONFIDENCE", "HIGH CONFIDENCE"],
      rows: MATRIX_BANDS.map(band => [
        { text: band, bold: true, fill: SEVERITY_FILL[band] },
        ...MATRIX_CONFIDENCE.map<Cell>(conf => {
          const n = matrix.grid[band][conf].length;
          return { text: n > 0 ? `${n} ${n === 1 ? "article" : "articles"}` : "No articles", align: "center", ...matrixFill(n) };
        }),
      ]),
      widths: [26, 25, 25, 25],
    });
    if (matrix.unplaced > 0) {
      rc.push({ type: "text", style: "note", text: `${matrix.unplaced} flagged ${matrix.unplaced === 1 ? "article has" : "articles have"} no confidence value and ${matrix.unplaced === 1 ? "is" : "are"} not shown in the grid.` });
    }

    rc.push({ type: "heading", level: 3, text: "Flagged Articles" });
    const shown = riskDocs.slice(0, MAX_FLAGGED_ROWS);
    const wn = windowNote(riskDocs.length, tiles ? tiles.flagged : null);
    if (wn) rc.push({ type: "text", text: wn, style: "note" });
    if (riskDocs.length > shown.length) {
      rc.push({ type: "text", style: "note", text: `Listing the first ${shown.length} of ${riskDocs.length} flagged articles.` });
    }
    if (shown.length === 0) {
      rc.push({ type: "text", text: "No flagged articles." });
    } else {
      rc.push({
        type: "table",
        landscape: true,
        compact: true,
        columns: ["Headline", "Score", "Severity", "Source", "Date (IST)", "Sentiment", "Topic"],
        widths: [88, 14, 20, 40, 34, 22, 36],
        rows: shown.map(d => [
          clean(d.title),
          { text: isScore100(d.risk_exact ?? d.risk) ? formatScore(d.risk_exact ?? d.risk) : NA, align: "center", bold: true },
          { text: String(d.severity), align: "center", fill: SEVERITY_FILL[d.severity] },
          clean(d.source) || "Unknown Source",
          d.timestamp ? `${formatIST(d.timestamp) ?? NA}${d.date_basis === "collected" ? " (collected)" : ""}` : NA,
          typeof d.risk_sentiment === "string" ? d.risk_sentiment : UNAVAILABLE_TEXT,
          clean(d.topic) || NA,
        ]),
      });
    }
  }
  sections.push({ id: "risk-center", title: "Risk Center", blocks: rc });

  // ---------------------------------------------------------------- Executive Analytics
  const ea: Block[] = [];
  const reputationBlock = summaryFailed ? null : summary?.reputation;
  const kv = overviewKpiValues({ reputation: reputationBlock, topicDistData: i.analytics.topicDistData, sentimentDistData: i.analytics.sentimentDistData });
  const overviewFailed = !!i.documentsError || !!i.historyError;
  ea.push({ type: "heading", level: 2, text: "Reputation & Sentiment History" });
  if (overviewFailed) {
    ea.push(unavailable());
  } else {
    ea.push({
      type: "stats",
      items: [
        { label: "Current Reputation", value: kv.currentReputation, sub: "Overall reputation score" },
        { label: "Sentiment Score", value: isUnitScore(kv.sentimentScore) ? formatSentimentScoreKpi(kv.sentimentScore) : NA, sub: kv.hasEnoughSentimentData ? "How positive coverage is (-1.0 to +1.0)" : "Awaiting more coverage to compute" },
        { label: "Topics Covered", value: kv.topicsCovered > 0 ? String(kv.topicsCovered) : NA, sub: "Distinct topics found in coverage" },
        { label: "Positive share (document sentiment)", value: isScore100(kv.positiveShare) ? `${kv.positiveShare.toFixed(0)}%` : NA, sub: "Favorable media percentage" },
      ],
    });
    ea.push({ type: "text", style: "muted", text: "Positive share (document sentiment): the share of articles whose sentiment score is above +0.3 (Negative: below -0.3, Neutral: in between). It counts articles, so it does not match the Positive mentions (brand-gated) on Brand Equity." });

    ea.push({ type: "heading", level: 3, text: "Sentiment Breakdown" });
    if (i.analytics.sentimentDistData.length > 0) {
      ea.push({ type: "chart", id: "sentiment", title: "Sentiment Breakdown", caption: captions.sentiment });
      ea.push({
        type: "table", compact: true, columns: ["Sentiment", "Articles"], widths: [60, 30],
        rows: i.analytics.sentimentDistData.map(d => [clean(d.name), { text: cnt(d.value), align: "right" }]),
      });
    } else {
      ea.push({ type: "text", text: "No sentiment distribution data." });
    }

    ea.push({ type: "heading", level: 3, text: "Coverage by Topic" });
    if (i.analytics.topicDistData.length > 0) {
      ea.push({ type: "chart", id: "topics", title: "Coverage by Topic", caption: captions.topics });
      // The screen shows these numbers only on hover; on paper they are printed.
      ea.push({
        type: "table", compact: true, columns: ["Topic", "Articles"], widths: [60, 30],
        rows: i.analytics.topicDistData.map(d => [clean(d.name), { text: cnt(d.value), align: "right" }]),
      });
      ea.push({ type: "text", style: "note", text: "Topics with fewer than 5 articles are not shown." });
    } else {
      ea.push({ type: "text", text: "No topics mapped." });
    }

    ea.push({ type: "heading", level: 3, text: "Reputation Score History" });
    const mc = scoringMethodChange(i.repHistory);
    if (mc.hasEarlier) ea.push({ type: "text", style: "note", text: SCORING_CHANGE_NOTE });
    if (i.repHistory.length > 0) {
      ea.push({ type: "chart", id: "repHistory", title: "Reputation Score History", caption: captions.repHistory });
      // Hover-only on screen; printed here with the IST time of each stored score (oldest first, as on the chart).
      ea.push({
        type: "table", compact: true, columns: ["Scored at (IST)", "Reputation score"], widths: [60, 30],
        rows: i.repHistory.map(h => [formatIST(h.rawDate) ?? NA, { text: isScore100(h.score) ? h.score.toFixed(2) : NA, align: "right" }]),
      });
    } else {
      ea.push({ type: "text", text: "No historical reputation data available." });
    }
  }

  ea.push({ type: "heading", level: 2, text: "Risk & Alert Profile" });
  const riskProfileFailed = !!i.documentsError || !!i.alertsError;
  // facts.openAlerts reads an unusable count as 0, which would say "No open alerts"; check the raw counts instead.
  const alertCountsOk = i.analytics.alertTimelineData.every(d => isCount(d?.count));
  if (riskProfileFailed) {
    ea.push(unavailable());
  } else {
    ea.push({
      type: "stats",
      items: [
        { label: "Documents Analyzed", value: facts.visibleTotal === null ? UNAVAILABLE_TEXT : String(facts.visibleTotal), sub: "All articles collected for this client, risky or not" },
        { label: "Avg Risk Score (Listed Feed)", value: facts.avgRiskVal === null ? UNAVAILABLE_TEXT : isScore100(facts.avgRiskVal) ? facts.avgRiskVal.toFixed(2) : NA, sub: `Average over the ${cnt(facts.scoredCount)} scored articles listed here, zero-risk ones included` },
        { label: "Critical-Risk Documents", value: riskStats?.scored === 0 || riskBad ? NA : facts.criticalTotal === null ? UNAVAILABLE_TEXT : String(facts.criticalTotal), sub: `Risk score ${HIGH_MAX + 1}+, all articles` },
        { label: "Alert Status", value: alertCountsOk ? facts.alertsStatus : NA, sub: !alertCountsOk ? "Alert counts could not be read" : facts.openAlerts === 0 ? "Nothing unacknowledged" : "Unacknowledged alerts" },
      ],
    });
    if (facts.loadedNote) ea.push({ type: "text", text: facts.loadedNote, style: "note" });

    ea.push({ type: "heading", level: 3, text: "Risk by Severity & Confidence" });
    const flaggedInList = flaggedDocs(i.analytics.riskMatrixData);
    const em = buildMatrix(flaggedInList);
    ea.push({
      type: "table",
      columns: ["Severity", "LOW CONFIDENCE", "MED CONFIDENCE", "HIGH CONFIDENCE"],
      widths: [26, 25, 25, 25],
      rows: MATRIX_BANDS.map(band => [
        { text: band, bold: true, fill: SEVERITY_FILL[band] },
        ...MATRIX_CONFIDENCE.map<Cell>(conf => {
          const n = em.grid[band][conf].length;
          return { text: n > 0 ? `${n} ${n === 1 ? "Document" : "Documents"}` : "0", align: "center", ...matrixFill(n) };
        }),
      ]),
    });
    const mw = windowNote(flaggedInList.length, facts.flaggedTotal);
    if (mw) ea.push({ type: "text", style: "note", text: mw });
    if (em.unplaced > 0) {
      ea.push({ type: "text", style: "note", text: `${em.unplaced} flagged ${em.unplaced === 1 ? "document carries" : "documents carry"} no confidence value and ${em.unplaced === 1 ? "is" : "are"} not placed in the matrix.` });
    }

    ea.push({ type: "heading", level: 3, text: "Daily Alerts Trigger Volume Timeline" });
    if (i.analytics.alertTimelineData.length === 0) {
      ea.push({ type: "text", text: "No open alerts. Nothing unacknowledged for this client." });
    } else {
      const st = alertTimelineStats(i.analytics.alertTimelineData);
      ea.push({ type: "chart", id: "alerts", title: "Daily Alerts Trigger Volume Timeline", caption: captions.alerts });
      const statsOk = alertCountsOk;
      ea.push({ type: "text", style: "muted", text: statsOk ? `Avg (${st.avg}) · Peak: ${st.peakCount}${st.peakDate ? ` on ${st.peakDate}` : ""}` : `Avg (${NA}) · Peak: ${NA}` });
    }

    ea.push({ type: "heading", level: 3, text: "Threat Concentration Heatmap (Severity × Topic)" });
    const hm = i.analytics.riskHeatmapData;
    const heatmapReadable = !hm || !hm.categories || (hm.categories as string[]).every(cat => (hm.severities as string[]).every(sev => { const c = hm.grid?.[cat]?.[sev]; return !c || isCount(c.count); }));
    if (!hm || !hm.categories || hm.categories.length === 0) {
      ea.push({ type: "text", text: "No active risk events." });
    } else if (!heatmapReadable) {
      ea.push({ type: "text", text: `${NA} (the heatmap counts could not be read).` });
    } else {
      const { rowTotals, colTotals, grandTotal } = heatmapTotals(hm);
      const pct = (n: number, d: number) => (d > 0 ? ((n / d) * 100).toFixed(0) : "0");
      const rows: Cell[][] = hm.categories.map((cat: string) => {
        const rowTot = rowTotals[cat] || 0;
        return [
          { text: clean(cat), bold: true },
          ...(hm.severities as string[]).map<Cell>((sev: string) => {
            const c = hm.grid[cat]?.[sev] || { count: 0, avgRisk: 0, avgSentiment: 0 };
            if (c.count === 0) return { text: "0", align: "center" };
            return {
              text: `${c.count} (${pct(c.count, rowTot)}%)\nRisk Score: ${isScore100(c.avgRisk) ? c.avgRisk.toFixed(0) : NA}\nSentiment: ${isUnitScore(c.avgSentiment) ? c.avgSentiment.toFixed(1) : NA}`,
              align: "center", fill: heatmapFill(sev, c.count),
            };
          }),
          { text: String(rowTot), align: "center", bold: true },
          { text: `${pct(rowTot, grandTotal)}%`, align: "center" },
        ];
      });
      rows.push([
        { text: "COLUMN TOTALS", bold: true },
        ...(hm.severities as string[]).map<Cell>((sev: string) => ({ text: `${colTotals[sev] || 0} (${pct(colTotals[sev] || 0, grandTotal)}%)`, align: "center", bold: true })),
        { text: String(grandTotal), align: "center", bold: true },
        { text: "100%", align: "center" },
      ]);
      ea.push({
        type: "table", landscape: true,
        columns: ["Topic category", "LOW", "MEDIUM", "HIGH", "CRITICAL", "ROW TOTAL", "DIST %"],
        widths: [52, 34, 34, 34, 34, 26, 22],
        rows,
      });
      ea.push({ type: "text", style: "note", text: "Articles that have not been risk-scored are not counted in the heatmap. Topics with fewer than 5 articles are not shown." });
    }
  }
  sections.push({ id: "executive-analytics", title: "Executive Analytics", blocks: ea });

  // ---------------------------------------------------------------- Footnotes
  footnotes.push(`Charts, the severity × confidence matrices, the heatmap and the flagged-articles table are built from the newest ${ARTICLE_WINDOW} articles at most (the dashboard loads ${i.analytics.riskMatrixData.length} for this client); tile totals count every article.`);
  if (scoringMethodChange(i.repHistory).hasEarlier) footnotes.push(SCORING_CHANGE_NOTE);
  footnotes.push("Dates and times in this report are in IST (Asia/Kolkata), except the day labels on charts, which use the browser's time zone, and the alert 'When' text, which is printed as the system recorded it.");
  footnotes.push(`Time zone used for the chart day labels: ${i.browserTimeZone || "unknown"}.`);

  const dataWindow: string[] = [];
  dataWindow.push(
    facts.visibleTotal !== null
      ? `Articles: newest ${i.analytics.riskMatrixData.length} of ${facts.visibleTotal} (the dashboard loads at most ${ARTICLE_WINDOW})`
      : `Articles: newest ${i.analytics.riskMatrixData.length} loaded (the dashboard loads at most ${ARTICLE_WINDOW})`
  );
  const repAsOf = formatIST(summary?.reputation?.computed_at);
  if (repAsOf) dataWindow.push(`Reputation score as of ${repAsOf}`);
  const riskAsOf = isRec(docRisk) && typeof docRisk.as_of === "string" ? formatIST(docRisk.as_of) : null;
  if (riskAsOf) dataWindow.push(`Risk scores as of ${riskAsOf}`);

  return {
    meta: {
      title: "XOOP | Reputation Report",
      clientName: name,
      generatedAt: formatIST(i.generatedAt) ?? "",
      userEmail: i.userEmail,
      dataWindow,
      guide: readingGuide(),
      fileName: reportFileName(name, i.generatedAt),
    },
    sections,
    footnotes,
  };

}
