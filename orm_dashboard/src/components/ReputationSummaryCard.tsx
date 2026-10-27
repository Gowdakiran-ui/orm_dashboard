import React, { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { buildBrandEquityView } from "@/utils/brandEquity";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, mutedText, SPECULAR_LINE } from "@/components/theme/tokens";
import { HeroGlass } from "@/components/theme/HeroGlass";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { ReputationScoreDefinition, ReputationGradeDefinition, RiskCountSummaryDefinition, RiskSignalsDefinition, AverageRiskScoreTrackedDefinition, EntitySentimentSplitDefinition, ShareOfVoiceDefinition } from "@/lib/metricDefinitions";
import { useTabNavigation } from "@/hooks/useTabNavigation";

export interface ReputationSummaryCardProps {
  reputationSummaryLoading: boolean;
  reputationSummaryError: string | null;
  reputationSummary: any;
  planAdvisory?: any;
  planAdvisoryLoading?: boolean;
  planAdvisoryError?: string | null;
  executives: any[];
  executivesLoading?: boolean;
  executivesError?: string | null;
  activeClientName: string;
  normalizedBenchmarks?: any[];
  benchmarksLoading?: boolean;
  benchmarksError?: string | null;
}

// Same severity classification as Risk Center (RiskTab.tsx).
const RISK_COLOR: Record<string, string> = {
  CRITICAL: "text-red-500",
  HIGH: "text-orange-500",
  MEDIUM: "text-yellow-500",
  NONE: "text-emerald-500",
};

// Small-caps section header / body text styling, deterministic/template-based
// text (no LLM call). Theme-aware functions instead of static strings since
// the accent + border now depend on light/dark glass mode.
function sectionLabelClass(isDark: boolean, withInlineIcon = false) {
  return `text-xs font-bold uppercase tracking-wider ${withInlineIcon ? "flex items-center gap-1" : "block"} border-b pb-1 ${
    isDark ? "text-[#00F5D4] border-white/[0.12]" : "text-[#3B82F6] border-black/[0.06]"
  }`;
}
function sectionTextClass(isDark: boolean) {
  return `text-xs leading-relaxed font-mono mt-1.5 ${isDark ? "text-zinc-300" : "text-zinc-600"}`;
}

export function ReputationSummaryCard({
  reputationSummaryLoading,
  reputationSummaryError,
  reputationSummary,
  planAdvisory,
  planAdvisoryLoading = false,
  planAdvisoryError = null,
  executives = [],
  executivesLoading = false,
  executivesError = null,
  activeClientName,
  normalizedBenchmarks = [],
  benchmarksLoading = false,
  benchmarksError = null,
}: ReputationSummaryCardProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const { navigateTo } = useTabNavigation();

  // Every number and sentence on this page comes from buildBrandEquityView (utils/brandEquity.ts),
  // which the exported report reads too. A failed or still-loading source renders "Unavailable" / a
  // placeholder, never a believable zero (the data hook turns a failed fetch into an empty list + error flag).
  const view = useMemo(
    () => buildBrandEquityView({
      reputationSummary, planAdvisory, planAdvisoryLoading, planAdvisoryError,
      executives, executivesLoading, executivesError, activeClientName,
      normalizedBenchmarks, benchmarksLoading, benchmarksError,
    }),
    [reputationSummary, planAdvisory, planAdvisoryLoading, planAdvisoryError, executives, executivesLoading, executivesError, activeClientName, normalizedBenchmarks, benchmarksLoading, benchmarksError]
  );
  const { riskStats } = view;

  if (reputationSummaryLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-8 font-mono">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className={`h-24 rounded-3xl ${glassTokens[theme].card}`} />
          ))}
        </div>
        <div className={`h-20 rounded-3xl ${glassTokens[theme].card}`} />
      </div>
    );
  }

  if (reputationSummaryError || !reputationSummary) {
    return (
      <Card className={`${glassCard(theme)} border-red-500/20 h-32`}>
        <TelemetryErrorWidget title="Summary Telemetry Offline" message={reputationSummaryError || "No data"} />
      </Card>
    );
  }

  const { sentiment, scoreKnown, scoreDisplay, gradeDisplay, asOf, scoreStatusText, verdict, overviewText, riskProfile, sentimentText, peopleText, standingText, alertLine } = view;

  const UNAVAILABLE = "Unavailable";
  const riskValue = (n: number | undefined) => (riskStats && n !== undefined ? n : UNAVAILABLE);

  const reputationScoreAndGradeDef = (
    <>
      <ReputationScoreDefinition />
      <span className="mt-2 block" />
      <ReputationGradeDefinition />
    </>
  );

  // Overview risk-count breakdown drill-through: each severity count
  // navigates to Risk Center pre-filtered to that severity band.
  const severityCountLink = (count: number, word: string, severity: string, colorClass: string) => (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); navigateTo("risk", { severity }); }}
      className={`hover:underline ${colorClass}`}
    >
      {count} {word}
    </button>
  );
  // All-history headline, with the last-365-days count beside it in plain words.
  const riskSignalsSub = riskStats && riskStats.dangerCount365 !== null
    ? `Critical + High documents, all time · ${riskStats.dangerCount365} in the last 365 days`
    : "Critical + High documents, all time";
  const severityBreakdownSub = riskStats ? (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
      {severityCountLink(riskStats.critical, "Critical", "critical", "text-red-500")}
      {severityCountLink(riskStats.high, "High", "high", "text-orange-500")}
      {severityCountLink(riskStats.medium, "Medium", "medium", "text-yellow-600")}
    </span>
  ) : (
    "Risk data unavailable"
  );

  const cards: Array<{
    label: string;
    value: React.ReactNode;
    sub: React.ReactNode;
    color: string;
    highlight?: boolean;
    compactValue?: boolean;
    def?: React.ReactNode;
    onClick?: () => void;
  }> = [
    { label: "Reputation Score", value: scoreDisplay, sub: scoreKnown ? `Grade ${gradeDisplay}${asOf ? ` · as of ${asOf}` : ""}` : scoreStatusText, color: "text-[#D4AF37]", highlight: true, def: reputationScoreAndGradeDef },
    { label: "Risk Signals", value: riskValue(riskStats?.dangerCount), sub: riskSignalsSub, color: !riskStats ? "text-zinc-400" : riskStats.dangerCount > 0 ? "text-red-500" : "text-emerald-500", highlight: true, def: <RiskSignalsDefinition /> },
    { label: "Total Risks Tracked (all time)", value: riskValue(riskStats?.total), sub: severityBreakdownSub, color: !riskStats ? "text-zinc-400" : RISK_COLOR[riskStats.dominantLevel], def: <RiskCountSummaryDefinition />, onClick: () => navigateTo("risk") },
    { label: "Positive Mentions", value: sentiment.positive, sub: "in coverage", color: "text-emerald-400", def: <EntitySentimentSplitDefinition /> },
    { label: "Overall Tone", value: sentiment.dominant ?? "N/A", sub: `${sentiment.positive} positive / ${sentiment.neutral} neutral / ${sentiment.negative} negative`, color: "text-emerald-400", def: <EntitySentimentSplitDefinition /> },
  ];

  // Only the Reputation Score tile (index 0) gets the full spotlight glass
  // treatment; everything else gets the plain glass-card base style.
  const statCardBody = (card: (typeof cards)[number]) => (
    <>
      <span className={`text-xs ${mutedText(theme)} uppercase tracking-wider flex items-center gap-1 mb-2`}>
        {card.label}
        {card.def && <InfoTooltip label={`About ${card.label}`}>{card.def}</InfoTooltip>}
      </span>
      <div>
        {card.onClick ? (
          <button
            type="button"
            onClick={card.onClick}
            title={typeof card.value === "string" ? card.value : undefined}
            className={`${card.highlight && !card.compactValue ? "text-2xl" : "text-xl"} font-bold block truncate text-left hover:underline ${card.color}`}
          >
            {card.value}
          </button>
        ) : (
          <span title={typeof card.value === "string" ? card.value : undefined} className={`${card.highlight && !card.compactValue ? "text-2xl" : "text-xl"} font-bold block truncate ${card.color}`}>{card.value}</span>
        )}
        {card.sub && <span className={`text-xs ${mutedText(theme)} block truncate mt-1`}>{card.sub}</span>}
      </div>
    </>
  );

  // Render-order/label split of the same `cards` data: highlight tiles first.
  const heroCards = cards.map((card, idx) => ({ card, idx })).filter(({ card }) => card.highlight);
  const detailCards = cards.map((card, idx) => ({ card, idx })).filter(({ card }) => !card.highlight);

  return (
    <div className="space-y-6">
      <div className={`${glassCard(theme)} p-4 flex flex-wrap items-center justify-between gap-3`}>
        <span className={`text-sm font-mono ${isDark ? "text-zinc-100" : "text-zinc-800"}`}>
          <span className="mr-2" aria-hidden="true">{verdict.emoji}</span>
          {verdict.text}
        </span>
        {verdict.actionLabel && verdict.action === "risk" && (
          <button
            type="button"
            onClick={() => navigateTo("risk")}
            className="text-sm font-mono font-semibold whitespace-nowrap hover:underline shrink-0"
            style={{ color: accent }}
          >
            {verdict.actionLabel}
          </button>
        )}
      </div>

      <div className="space-y-3">
        <span className={`text-xs font-mono uppercase tracking-wider block ${mutedText(theme)}`}>At a Glance</span>
        <div className="grid gap-4 sm:grid-cols-2 font-mono">
          {heroCards.map(({ card, idx }) =>
            idx === 0 ? (
              <HeroGlass key={idx} theme={theme} className="p-4 flex flex-col justify-between min-w-0">
                {statCardBody(card)}
              </HeroGlass>
            ) : (
              <div key={idx} className={`${glassCard(theme)} p-4 flex flex-col justify-between min-w-0`}>
                <div className={SPECULAR_LINE} />
                {statCardBody(card)}
              </div>
            )
          )}
        </div>
      </div>

      <div className="space-y-3">
        <span className={`text-xs font-mono uppercase tracking-wider block ${mutedText(theme)}`}>More Detail</span>
        <div className="grid gap-4 sm:grid-cols-3 font-mono">
          {detailCards.map(({ card, idx }) => (
            <div key={idx} className={`${glassCard(theme)} p-4 flex flex-col justify-between min-w-0`}>
              <div className={SPECULAR_LINE} />
              {statCardBody(card)}
            </div>
          ))}
        </div>
      </div>

      <Card className={glassCard(theme)}>
        <div className={SPECULAR_LINE} />
        <CardContent className="p-4 space-y-4">
            <div>
              <span className={sectionLabelClass(isDark)}>Overview</span>
              <p className={sectionTextClass(isDark)}>{overviewText}</p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark, true)}>
                Risk Profile
                <InfoTooltip label="About Average Risk Score"><AverageRiskScoreTrackedDefinition /></InfoTooltip>
              </span>
              <p className={sectionTextClass(isDark)}>
                {riskProfile.kind !== "some" ? (
                  riskProfile.text
                ) : (
                  <>
                    {riskProfile.before}
                    <button type="button" onClick={() => navigateTo("risk")} className="hover:underline font-bold">{riskProfile.avg}</button>
                    {riskProfile.after}
                  </>
                )}
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark, true)}>
                Sentiment
                <InfoTooltip label="About mentions and tone"><EntitySentimentSplitDefinition /></InfoTooltip>
              </span>
              <p className={sectionTextClass(isDark)}>{sentimentText}</p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Notable People in Coverage</span>
              <p className={sectionTextClass(isDark)}>
                {peopleText}
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark, true)}>
                Competitive Standing
                <InfoTooltip label="About share of voice"><ShareOfVoiceDefinition /></InfoTooltip>
              </span>
              <p className={sectionTextClass(isDark)}>{standingText}</p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Alerts</span>
              <p className={sectionTextClass(isDark)}>{alertLine}</p>
            </div>
        </CardContent>
      </Card>
    </div>
  );
}
