import React from "react";
import { Check, HelpCircle, Minus } from "lucide-react";

// Landing-page comparison chart. Every competitor cell is Yes, Partial or Unknown, never "No": a vendor's public pages can show that a
// thing exists, not that it is missing. "Unknown" means we could not confirm it. A Yes or Partial cell is backed by a vendor page listed
// under "Sources" (each loaded and read on 10 November 2026). XOOP's own cells say what the product does today, including what it does
// not do yet.

export type ChartLevel = "yes" | "partial" | "unknown" | "no" | "planned" | "text";
export type ChartCell = { level: ChartLevel; note?: string };
export type ChartSource = { vendor: string; url: string };
export type ChartRow = {
  capability: string;
  xoop: ChartCell; meltwater: ChartCell; brandwatch: ChartCell; sprinklr: ChartCell; talkwalker: ChartCell;
  sources: ChartSource[];
  optional?: boolean;
};

const INK = "#0B2D54";
const INK_MUTED = "#4C5F82";
const INK_FAINT = "#7A8CAD";

export const CHART_COLUMNS = ["XOOP", "Meltwater", "Brandwatch", "Sprinklr", "Talkwalker"] as const;
// Two rows are optional (they show a gap or a difference of approach); set to false to leave them out.
export const SHOW_OPTIONAL_CHART_ROWS = true;

const U: ChartCell = { level: "unknown" };
const Y: ChartCell = { level: "yes" };

const MELTWATER_PR = "https://www.meltwater.com/en/products/pr-reporting";
const SPRINKLR_LISTENING = "https://www.sprinklr.com/products/consumer-intelligence/social-listening/";
const SPRINKLR_SENTIMENT = "https://www.sprinklr.com/help/articles/ai-enrichments/detect-the-sentiment-present-in-customer-messages-accurately/645b5278e66f2e36b45187ac/";
const MELTWATER_ALERTS = "https://www.meltwater.com/en/products/real-time-alerting";

export const chartRows: ChartRow[] = [
  {
    capability: "Sentiment scoring",
    xoop: { level: "yes", note: "English-language coverage" }, meltwater: Y, brandwatch: Y, sprinklr: Y, talkwalker: Y,
    sources: [
      { vendor: "Meltwater", url: MELTWATER_PR },
      { vendor: "Brandwatch", url: "https://www.brandwatch.com/p/sentiment-analysis/" },
      { vendor: "Sprinklr", url: SPRINKLR_SENTIMENT },
      { vendor: "Talkwalker", url: "https://www.hootsuite.com/fr/talkwalker" },
    ],
  },
  { capability: "Risk scoring with the reason shown", xoop: Y, meltwater: U, brandwatch: U, sprinklr: U, talkwalker: U, sources: [] },
  {
    capability: "Legal status on risk items (allegation, probe, charged, settled, dismissed)",
    xoop: { level: "yes", note: "from headlines" }, meltwater: U, brandwatch: U, sprinklr: U, talkwalker: U, sources: [],
  },
  { capability: "One incident per story", xoop: Y, meltwater: U, brandwatch: U, sprinklr: U, talkwalker: U, sources: [] },
  {
    capability: "Executive tracking with sources",
    xoop: Y, meltwater: { level: "partial", note: "manual named-entity setup" }, brandwatch: U, sprinklr: U, talkwalker: U,
    sources: [{ vendor: "Meltwater", url: "https://community.meltwater.com/use-case-playbooks-132/crisis-and-risk-management-playbook-3147" }],
  },
  {
    capability: "Competitor benchmarking",
    xoop: { level: "partial", note: "tracked competitors, 90 days" }, meltwater: Y, brandwatch: Y, sprinklr: Y, talkwalker: Y,
    sources: [
      { vendor: "Meltwater", url: MELTWATER_PR },
      { vendor: "Brandwatch", url: "https://www.brandwatch.com/p/share-of-voice/" },
      { vendor: "Sprinklr", url: SPRINKLR_LISTENING },
      { vendor: "Talkwalker", url: "https://www.talkwalker.com/use-cases/competitive-intelligence" },
    ],
  },
  {
    capability: "Alerting",
    xoop: { level: "partial", note: "in-app, after each refresh; no email yet" }, meltwater: Y,
    brandwatch: { level: "partial", note: "Signals, launched 2015" }, sprinklr: { level: "partial" }, talkwalker: Y,
    sources: [
      { vendor: "Meltwater", url: MELTWATER_ALERTS },
      { vendor: "Brandwatch", url: "https://www.brandwatch.com/press/press-releases/brandwatch-launches-signals-groundbreaking-automated-intelligence-alerts/" },
      { vendor: "Sprinklr", url: SPRINKLR_LISTENING },
      { vendor: "Talkwalker", url: "https://www.hootsuite.com/platform/crisis-management" },
    ],
  },
  {
    capability: "AI-answer visibility",
    xoop: { level: "partial", note: "analyst-run snapshot on request; no client self-serve" }, meltwater: { level: "yes", note: "add-on" },
    brandwatch: U, sprinklr: U, talkwalker: U,
    sources: [{ vendor: "Meltwater", url: "https://www.meltwater.com/en/products/genai-lens" }],
  },
  {
    capability: "Hindi sentiment",
    xoop: { level: "no" }, meltwater: U, brandwatch: U, sprinklr: { level: "yes", note: "Hindi" }, talkwalker: U,
    sources: [{ vendor: "Sprinklr", url: SPRINKLR_SENTIMENT }],
    optional: true,
  },
  {
    capability: "Automatic ongoing monitoring",
    xoop: { level: "no", note: "refresh on demand" }, meltwater: Y, brandwatch: U, sprinklr: U, talkwalker: U,
    sources: [{ vendor: "Meltwater", url: MELTWATER_ALERTS }],
    optional: true,
  },
  {
    capability: "Content removal",
    xoop: { level: "text", note: "Offered separately by Onlyne's removal service" }, meltwater: U, brandwatch: U, sprinklr: U, talkwalker: U, sources: [],
  },
];

export const chartLegend: { level: ChartLevel; label: string }[] = [
  { level: "yes", label: "Yes" }, { level: "partial", label: "Partial" }, { level: "unknown", label: "Unknown" },
  { level: "no", label: "No" }, { level: "planned", label: "Planned" },
];

export const CHART_FOOTNOTE = "Based on vendors' public documentation as of 10 November 2026. Unknown means we could not confirm it, not that it is absent.";

export function visibleChartRows(showOptional: boolean = SHOW_OPTIONAL_CHART_ROWS): ChartRow[] {
  return chartRows.filter(r => showOptional || !r.optional);
}

export function cellsOf(r: ChartRow): ChartCell[] {
  return [r.xoop, r.meltwater, r.brandwatch, r.sprinklr, r.talkwalker];
}

export function ChartMark({ level }: { level: ChartLevel }) {
  if (level === "yes") return <span className="inline-flex items-center gap-1.5 text-[#A57F37]"><Check className="h-4 w-4" strokeWidth={2.5} aria-hidden="true" />Yes</span>;
  if (level === "partial") return <span className="inline-flex items-center gap-1.5 text-[#A57F37]"><span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-[#A57F37]" aria-hidden="true" />Partial</span>;
  if (level === "planned") return <span className="inline-flex items-center gap-1.5" style={{ color: INK_MUTED }}><span className="inline-block h-2.5 w-2.5 rounded-full border border-dashed" style={{ borderColor: INK_MUTED }} aria-hidden="true" />Planned</span>;
  if (level === "no") return <span className="inline-flex items-center gap-1.5" style={{ color: INK_MUTED }}><Minus className="h-4 w-4" strokeWidth={2.5} aria-hidden="true" />No</span>;
  return <span className="inline-flex items-center gap-1.5" style={{ color: INK_FAINT }}><HelpCircle className="h-4 w-4" aria-hidden="true" />Unknown</span>;
}

function ChartCellView({ cell }: { cell: ChartCell }) {
  return (
    <div className="space-y-0.5" data-level={cell.level}>
      {cell.level !== "text" && <ChartMark level={cell.level} />}
      {cell.note && <span className="block text-xs leading-snug" style={{ color: INK_MUTED }}>{cell.note}</span>}
    </div>
  );
}

// Legend, table, footnote and sources. The section heading and background stay in app/page.tsx.
export function ComparisonChartBody({ showOptional = SHOW_OPTIONAL_CHART_ROWS }: { showOptional?: boolean }) {
  const rows = visibleChartRows(showOptional);
  const sourced = rows.filter(r => r.sources.length > 0);
  return (
    <>
      <ul className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-xs" aria-label="Legend" data-testid="chart-legend">
        {chartLegend.map(l => <li key={l.level}><ChartMark level={l.level} /></li>)}
      </ul>
      <div className="overflow-x-auto rounded-2xl border border-[#0B2D54]/12 bg-white shadow-[0_1px_3px_rgba(11,45,84,0.08)]">
        <table className="w-full min-w-[860px] border-collapse text-left text-sm">
          <thead>
            <tr className="bg-[#F3EFE3]">
              <th className="px-5 py-4 font-[family-name:var(--font-landing-display)] font-medium" style={{ color: INK }}>Capability</th>
              {CHART_COLUMNS.map(c => (
                <th key={c} className={`px-4 py-4 font-[family-name:var(--font-landing-display)] font-medium ${c === "XOOP" ? "text-[#A57F37]" : ""}`} style={c === "XOOP" ? undefined : { color: INK_MUTED }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={row.capability} className={idx > 0 ? "border-t border-[#0B2D54]/10" : ""} data-testid="chart-row">
                <td className="px-5 py-4" style={{ color: INK }}>{row.capability}</td>
                {cellsOf(row).map((cell, i) => (
                  <td key={CHART_COLUMNS[i]} className={`px-4 py-4 align-top ${i === 0 ? "bg-[#CEA555]/8" : ""}`}><ChartCellView cell={cell} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-[0.8rem]" style={{ color: INK_FAINT }} data-testid="chart-footnote">{CHART_FOOTNOTE}</p>
      <details className="mt-3 text-[0.8rem]" style={{ color: INK_FAINT }}>
        <summary className="cursor-pointer">Sources</summary>
        <ul className="mt-2 space-y-1.5">
          {sourced.map(r => (
            <li key={r.capability}>
              <span className="font-medium" style={{ color: INK_MUTED }}>{r.capability}: </span>
              {r.sources.map((src, i) => (
                <React.Fragment key={src.url + src.vendor}>
                  {i > 0 && ", "}
                  <a href={src.url} target="_blank" rel="noopener noreferrer" className="underline decoration-dotted underline-offset-2">{src.vendor}</a>
                </React.Fragment>
              ))}
            </li>
          ))}
        </ul>
      </details>
    </>
  );
}
