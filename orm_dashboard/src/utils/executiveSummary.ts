// The Executive Summary page of the exported report: a pure function from the report model's existing values to the
// cards and sentences printed on page 2. No new calculations, no clock, no React.
//
// Wording rule: sentences are templates filled with values the model already holds. There is NO trend or direction
// language anywhere (XOOP has no trend detection), and no prose beyond what already exists in the report.
import type { ReportFacts } from "@/utils/reportModel";

export const TOP_RISKS_SHOWN = 3;
export const OPEN_ALERTS_SHOWN = 3;
export const TOP_TOPICS_SHOWN = 3;
export const NOT_ENOUGH_DATA = "Not enough data yet";
const NA = "N/A";
const UNAVAILABLE = "Unavailable";

export interface SummaryKpi { label: string; value: string; sub: string }
export interface SummaryRisk { title: string; severity: string; source: string; date: string; score: string }
export interface SummaryAlert { title: string; severity: string; raised: string }
export interface ExecutiveSummary {
  clientName: string;
  headline: { score: string; grade: string; asOf: string | null; known: boolean };
  kpis: SummaryKpi[];
  sentences: string[];
  topRisks: SummaryRisk[];
  topRisksNote: string | null; // "+N more" / empty-state text
  openAlerts: SummaryAlert[];
  openAlertsNote: string | null;
  tone: { state: "ok" | "na" | "unavailable"; positive: number; neutral: number; negative: number } | null;
  toneLabel: string;
  topTopics: { name: string; count: number }[];
  topicsNote: string | null;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);
// Display strings from the model are numbers, "N/A" or "Unavailable"; only real numbers go into a sentence.
const asCount = (v: string): number | null => (/^\d+$/.test(v) ? Number(v) : null);

export function buildExecutiveSummary(f: ReportFacts, clientName: string): ExecutiveSummary {
  const risk = f.risk;
  const flagged = asCount(risk.total);
  const critical = asCount(risk.critical), high = asCount(risk.high), medium = asCount(risk.medium);
  const splitKnown = critical !== null && high !== null && medium !== null;
  const openCount = f.alerts.state === "ok" ? f.alerts.items.length : null;
  const toneCounts = f.tone.positive !== null && f.tone.neutral !== null && f.tone.negative !== null
    ? { positive: f.tone.positive, neutral: f.tone.neutral, negative: f.tone.negative } : null;

  const kpis: SummaryKpi[] = [
    {
      label: "Reputation Score",
      value: f.score.state === "unavailable" ? UNAVAILABLE : f.score.display,
      sub: f.score.state === "ok" ? `Grade ${f.score.grade}` : f.score.state === "na" ? (f.score.statusText || NOT_ENOUGH_DATA) : "Data could not be loaded",
    },
    {
      label: "Risk Signals", value: risk.signals,
      sub: risk.state === "ok" ? "Critical + High" : risk.state === "na" ? "No risk-scored articles yet" : "Data could not be loaded",
    },
    {
      label: "Flagged Articles", value: risk.total,
      sub: risk.state === "ok" && splitKnown ? `${critical} Critical · ${high} High · ${medium} Medium` : risk.state === "na" ? "No risk-scored articles yet" : "Data could not be loaded",
    },
    {
      label: "Active Alerts", value: openCount === null ? UNAVAILABLE : String(openCount),
      sub: openCount === null ? "Data could not be loaded" : openCount === 0 ? "None open" : "Unacknowledged",
    },
    {
      label: "Overall Tone", value: f.tone.state === "unavailable" ? UNAVAILABLE : f.tone.dominant ?? NA,
      sub: toneCounts ? `${toneCounts.positive} positive · ${toneCounts.neutral} neutral · ${toneCounts.negative} negative` : f.tone.state === "unavailable" ? "Data could not be loaded" : "No sentiment readings yet",
    },
    { label: "Documents Analyzed", value: f.documentsAnalyzed, sub: "All articles collected" },
  ];

  // "What happened": 3 to 5 template sentences over existing values.
  const sentences: string[] = [];
  if (f.score.state === "ok") sentences.push(f.texts.overview);
  else if (f.score.state === "na") sentences.push(`${clientName}: ${f.score.statusText || NOT_ENOUGH_DATA}.`);
  else sentences.push(`${clientName}: reputation data is unavailable.`);

  if (risk.state === "ok" && flagged !== null && splitKnown) {
    sentences.push(flagged === 0
      ? "No articles carry a risk above Low."
      : `${flagged} ${plural(flagged, "article carries", "articles carry")} a risk above Low: ${critical} Critical, ${high} High and ${medium} Medium.`);
  } else if (risk.state === "na") sentences.push("No articles have been risk-scored yet, so there are no risk figures.");
  else sentences.push("Risk figures are unavailable.");

  const top = f.topRisks[0];
  if (risk.state === "ok" && flagged !== null && flagged > 0 && top) {
    sentences.push(`The highest-risk article is "${top.title}" (${top.score} pts, ${top.severity.charAt(0) + top.severity.slice(1).toLowerCase()}), from ${top.source}.`);
  }

  if (openCount === null) sentences.push("Alert data is unavailable.");
  else sentences.push(openCount === 0 ? "There are no open alerts." : `There ${plural(openCount, "is", "are")} ${openCount} open ${plural(openCount, "alert", "alerts")}.`);

  if (toneCounts && f.tone.dominant) sentences.push(f.texts.sentiment);
  else if (f.tone.state === "ok") sentences.push("No mentions with a sentiment reading yet.");

  const topRisks = f.topRisks.slice(0, TOP_RISKS_SHOWN);
  let topRisksNote: string | null = null;
  if (risk.state === "unavailable") topRisksNote = "Unavailable (data could not be loaded)";
  else if (f.topRisks.length === 0) topRisksNote = risk.state === "na" ? NOT_ENOUGH_DATA : "No flagged articles.";
  else if (f.topRisks.length > topRisks.length) topRisksNote = `+${f.topRisks.length - topRisks.length} more in the Risk Center`;

  const openAlerts = f.alerts.items.slice(0, OPEN_ALERTS_SHOWN).map(a => ({ title: a.title, severity: a.severity, raised: a.raised }));
  const openAlertsNote = f.alerts.state === "unavailable" ? "Unavailable (data could not be loaded)"
    : f.alerts.items.length === 0 ? "No open alerts."
    : f.alerts.items.length > openAlerts.length ? `+${f.alerts.items.length - openAlerts.length} more in the Risk Center` : null;

  const topTopics = f.topics.items.slice(0, TOP_TOPICS_SHOWN);
  const topicsNote = f.topics.state === "unavailable" ? "Unavailable (data could not be loaded)" : topTopics.length === 0 ? NOT_ENOUGH_DATA : null;

  return {
    clientName,
    headline: { score: f.score.state === "unavailable" ? UNAVAILABLE : f.score.display, grade: f.score.grade, asOf: f.score.asOf, known: f.score.state === "ok" },
    kpis, sentences, topRisks, topRisksNote, openAlerts, openAlertsNote,
    tone: toneCounts ? { state: f.tone.state, ...toneCounts } : null,
    toneLabel: f.tone.state === "unavailable" ? UNAVAILABLE : f.tone.dominant ?? NA,
    topTopics, topicsNote,
  };
}
