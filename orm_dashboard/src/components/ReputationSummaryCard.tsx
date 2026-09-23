import React, { useMemo, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { getRiskLevel, RISK_THRESHOLDS } from "@/utils/riskLevel";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, mutedText, bodyText, GRADIENT_HEADING_CLASS, gradientHeadingStyle, SPECULAR_LINE } from "@/components/theme/tokens";
import { HeroGlass } from "@/components/theme/HeroGlass";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { ReputationScoreDefinition, ReputationGradeDefinition, RiskCountSummaryDefinition, AverageRiskScoreTrackedDefinition, CompetitorRankShareOfVoiceDefinition, EntitySentimentSplitDefinition } from "@/lib/metricDefinitions";
import { useTabNavigation } from "@/hooks/useTabNavigation";

export interface ReputationSummaryCardProps {
  reputationSummaryLoading: boolean;
  reputationSummaryError: string | null;
  reputationSummary: any;
  planAdvisory?: any;
  planAdvisoryLoading?: boolean;
  planAdvisoryError?: string | null;
  documents: any[];
  documentsLoading?: boolean;
  executives: any[];
  executivesLoading?: boolean;
  clientRank: string;
  clientSOV: number;
  activeClientName: string;
  normalizedBenchmarks?: any[];
  repHistory?: any[];
}

// Same severity classification as Risk Center (RiskTab.tsx).
const RISK_COLOR: Record<string, string> = {
  CRITICAL: "text-red-500",
  HIGH: "text-orange-500",
  MEDIUM: "text-yellow-500",
  LOW: "text-emerald-500",
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
  documents = [],
  documentsLoading = false,
  executives = [],
  executivesLoading = false,
  clientRank,
  clientSOV,
  activeClientName,
  normalizedBenchmarks = [],
  repHistory = [],
}: ReputationSummaryCardProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const { navigateTo } = useTabNavigation();
  // Anchor for the top-of-page verdict line's "See what it's about" link,
  // when there's nothing more specific (an alert, a risk count) to jump
  // straight to -- scrolls down to the "What to do about it" card instead
  // of duplicating its content a second time near the top.
  const whatToDoRef = useRef<HTMLDivElement>(null);
  const scrollToWhatToDo = () => whatToDoRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  // Total risks + severity breakdown + avg risk score. Requires MEDIUM+
  // (RiskTab.tsx's Incident Command Register applies the same floor) --
  // a matched document with no RiskEvent row defaults to risk=0, and a
  // routine Positive/Neutral document can still score a few LOW points
  // from coverage volume alone (risk_engine.py); neither is a real risk.
  // Previously counted every scored document unconditionally, so this
  // panel reported "262 risks tracked" (244 of them LOW) in the same
  // breath Risk Center reported 18 -- same underlying data, two
  // contradictory totals for what counts as "a risk".
  const riskStats = useMemo(() => {
    const riskDocs = (documents || []).filter(d => d && typeof d.risk === "number" && d.risk > RISK_THRESHOLDS.LOW_TO_MEDIUM);
    const total = riskDocs.length;
    let critical = 0, high = 0, medium = 0, low = 0, sumScore = 0;
    riskDocs.forEach(d => {
      const level = getRiskLevel(d.risk);
      if (level === "CRITICAL") critical++;
      else if (level === "HIGH") high++;
      else if (level === "MEDIUM") medium++;
      else low++;
      sumScore += d.risk;
    });
    const avg = total > 0 ? (sumScore / total).toFixed(1) : "0.0";
    const dominantLevel = critical > 0 ? "CRITICAL" : high > 0 ? "HIGH" : medium > 0 ? "MEDIUM" : "LOW";
    // Top 1-2 highest-risk items named directly, same idea as the reference
    // panel naming "LEGAL RISK NARRATIVE - POTATO FARMERS..." rather than
    // just showing a count. Requires MEDIUM+ (RiskTab.tsx's Incident Command
    // Register applies the same floor) -- naming a LOW-severity item (e.g. a
    // profit-surge story that only scored a few points from coverage volume)
    // as "the highest-risk item" misrepresents it as a real incident.
    const topRiskDocs = [...riskDocs]
      .filter(d => (d.risk || 0) > RISK_THRESHOLDS.LOW_TO_MEDIUM)
      .sort((a, b) => (b.risk || 0) - (a.risk || 0))
      .slice(0, 2);
    return { total, critical, high, medium, low, avg, dominantLevel, dangerCount: critical + high, topRiskDocs };
  }, [documents]);

  // Most mentioned executive + tracked leaders count. Highest/lowest scoring
  // executive uses the same `.score` field and `?? 0` fallback as
  // ExecutivesTab's summary memo (ExecutivesTab.tsx lines 97-99).
  const execStats = useMemo(() => {
    // `document_count` (client_intelligence.py's get_client_executives) is
    // the same real, already-computed mention count ExecutivesTab's
    // gradeDriverLine already surfaces per-executive -- previously this
    // sorted by `mention_count`, a field that never existed anywhere in
    // this response, so it silently showed whichever executive the DB
    // happened to return first. Only executives with a real count are
    // considered; a name tiebreak keeps ties deterministic instead of
    // depending on incidental DB row order.
    // null (not a placeholder string) when there's no executive to name --
    // callers must handle the zero-executive case explicitly rather than
    // rendering this value unconditionally into name-shaped UI.
    const mostMentioned = [...executives]
      .filter(e => typeof e.document_count === "number")
      .sort((a, b) => (b.document_count - a.document_count) || a.name.localeCompare(b.name))[0]?.name || null;
    const sortedByScore = [...executives].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    const highest = sortedByScore[0] || null;
    const lowest = sortedByScore.length > 0 ? sortedByScore[sortedByScore.length - 1] : null;
    return { total: executives.length, mostMentioned, highest, lowest };
  }, [executives]);

  // Top-ranked competitor for contrast, using the backend `rank` field (0 =
  // unranked/no evidence -- same signal CompetitorsTab.tsx treats as
  // canonical, see its rankedBrands memo comments).
  const topCompetitor = useMemo(() => {
    return (normalizedBenchmarks || []).find(b => b.rank === 1) || null;
  }, [normalizedBenchmarks]);

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

  const rep = reputationSummary.reputation || {};
  const sentiment = reputationSummary.sentiment || { positive: 0, neutral: 0, negative: 0, dominant: null };
  const execAlert = reputationSummary.executive_alert || { open: false, alert: null };

  const scoreKnown = rep.status === "ok" && rep.score != null;
  const scoreDisplay = scoreKnown ? rep.score.toFixed(2) : "N/A";
  const gradeDisplay = scoreKnown ? (rep.grade ?? "N/A") : "N/A";
  const trendDisplay = rep.trend ?? "STABLE";
  const sovDisplay = clientSOV.toFixed(1);
  // Trend Direction only updates when this client's pipeline is re-run
  // (Phase 15 -- collection/aggregation is trigger-driven, not continuous),
  // so it can go stale between runs with zero indication. Understated
  // context, not a warning -- same short-date convention CompetitorsTab's
  // PUBLISHED DATE column already uses.
  const trendAsOf = rep.computed_at
    ? new Date(rep.computed_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : null;

  const alertNames = execAlert.open && execAlert.alert?.entity_name ? execAlert.alert.entity_name : null;
  const alertSeverity = execAlert.open ? execAlert.alert?.severity ?? null : null;
  const alertLine = execAlert.open
    ? `1 open executive-risk alert: ${alertNames ?? "unknown"}.`
    : "No open executive-risk alerts.";
  // Severity preview so the tile itself signals how serious the alert is,
  // not just who it's about -- reuses the `severity` field already returned
  // by reputation-summary's `executive_alert.alert`, no new computation.
  const alertTileSub = execAlert.open
    ? `${alertNames ?? "Open alert"}${alertSeverity ? ` (${alertSeverity} — needs review)` : ""}`
    : "None open";

  // One-line top-of-page verdict + action, promoted from content that
  // already exists further down this same page (the alert line, the risk
  // danger count, and the AI Advisory / "What to do about it" paragraph) --
  // no new computation, just surfaced earlier so a 2-3 minute skim sees the
  // plain-language answer before the stat tiles. Priority matches the order
  // a reader should care about: an open executive alert first, then a
  // Critical/High risk count, then the AI Advisory's own lead sentence,
  // then an honest steady-state default naming what's being watched.
  const verdict: { emoji: string; text: string; actionLabel: string | null; onAction: (() => void) | null } =
    documentsLoading
      ? { emoji: "⏳", text: "Checking current risk activity…", actionLabel: null, onAction: null }
      : execAlert.open
      ? {
          emoji: alertSeverity === "CRITICAL" ? "🔴" : "🟡",
          text: `One alert needs your attention this week — ${alertNames ?? "an executive"}${alertSeverity ? ` (${alertSeverity})` : ""}. Coverage is otherwise ${trendDisplay === "DECLINING" ? "trending down" : "steady"}.`,
          actionLabel: "See what it's about →",
          onAction: () => navigateTo("risk"),
        }
      : riskStats.dangerCount > 0
      ? {
          emoji: "🟡",
          text: `${riskStats.dangerCount} risk${riskStats.dangerCount === 1 ? "" : "s"} flagged as Critical or High this week.`,
          actionLabel: "See what it's about →",
          onAction: () => navigateTo("risk"),
        }
      : planAdvisory?.lead
      ? {
          emoji: "🟡",
          text: planAdvisory.lead,
          actionLabel: "See what to do about it →",
          onAction: scrollToWhatToDo,
        }
      : {
          emoji: "🟢",
          text: `Your reputation is stable this week. Watching ${riskStats.total} tracked risk${riskStats.total === 1 ? "" : "s"}.`,
          actionLabel: null,
          onAction: null,
        };

  // documents/executives each load independently and can settle
  // at noticeably different times after a client switch (confirmed live:
  // reputationSummary -- which sentiment reads from -- lands well before
  // documents does), so a card computed off a still-loading source showed a
  // real "0 risks tracked" next to an already-correct, non-zero reputation
  // score for several real seconds -- a genuine, reproducible transient
  // misread risk, not a one-off glitch. "—" while loading is honest;
  // rendering the real zero before the real data has arrived is not.
  const LOADING_PLACEHOLDER = "—";
  const reputationScoreAndGradeDef = (
    <>
      <ReputationScoreDefinition />
      <span className="mt-2 block" />
      <ReputationGradeDefinition />
    </>
  );

  // Overview risk-count breakdown drill-through: each severity count
  // navigates to Risk Center pre-filtered to that severity band. Same
  // `navigateTo` helper every other drill-through in this task uses --
  // no one-off click handler.
  const severityCountLink = (count: number, word: string, severity: string, colorClass: string) => (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); navigateTo("risk", { severity }); }}
      className={`hover:underline ${colorClass}`}
    >
      {count} {word}
    </button>
  );
  const severityBreakdownSub = documentsLoading ? (
    "Loading..."
  ) : (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
      {severityCountLink(riskStats.critical, "Critical", "critical", "text-red-500")}
      {severityCountLink(riskStats.high, "High", "high", "text-orange-500")}
      {severityCountLink(riskStats.medium, "Medium", "medium", "text-yellow-600")}
      {severityCountLink(riskStats.low, "Low", "low", "text-emerald-500")}
    </span>
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
    { label: "Reputation Score", value: scoreDisplay, sub: scoreKnown ? `Grade ${gradeDisplay}` : "", color: "text-[#D4AF37]", highlight: true, def: reputationScoreAndGradeDef },
    { label: "Risk Signals", value: documentsLoading ? LOADING_PLACEHOLDER : riskStats.dangerCount, sub: "Critical + High", color: riskStats.dangerCount > 0 ? "text-red-500" : "text-emerald-500", highlight: true },
    { label: "Trend Direction", value: trendDisplay, sub: trendAsOf ? `Reputation momentum · as of ${trendAsOf}` : "Reputation momentum", color: "text-sky-500", highlight: true, compactValue: true },
    { label: "Total Risks Tracked", value: documentsLoading ? LOADING_PLACEHOLDER : riskStats.total, sub: severityBreakdownSub, color: RISK_COLOR[riskStats.dominantLevel], def: <RiskCountSummaryDefinition />, onClick: () => navigateTo("risk") },
    { label: "Positive Signals", value: sentiment.positive, sub: "Positive-sentiment entity mentions", color: "text-emerald-400", def: <EntitySentimentSplitDefinition /> },
    { label: "Dominant Sentiment", value: sentiment.dominant ?? "N/A", sub: `${sentiment.positive}/${sentiment.neutral}/${sentiment.negative} mentions`, color: "text-emerald-400", def: <EntitySentimentSplitDefinition /> },
    {
      label: "Most Mentioned Person",
      value: executivesLoading
        ? LOADING_PLACEHOLDER
        : execStats.mostMentioned ?? (
            <span className={`text-sm font-normal normal-case ${mutedText(theme)}`}>No executives tracked yet</span>
          ),
      sub: "Overall visibility",
      color: "text-sky-500",
    },
    { label: "Notable People Tracked", value: executivesLoading ? LOADING_PLACEHOLDER : execStats.total, sub: "Mentioned in coverage, not necessarily this client's own staff", color: "text-sky-500" },
    { label: "Competitor Rank / Share of Voice", value: clientRank, sub: `${sovDisplay}% share of voice`, color: "text-sky-500", def: <CompetitorRankShareOfVoiceDefinition /> },
    { label: "Executive Alerts", value: execAlert.open ? 1 : 0, sub: alertTileSub, color: execAlert.open ? "text-red-500" : "text-emerald-500" },
  ];

  // Only the Reputation Score tile (index 0 -- the single number this whole
  // panel exists to surface) gets the full spotlight + border-beam glass
  // treatment. Everything else, including the other "highlight" tiles, gets
  // the plain glass-card base style -- see the redesign report for why.
  const statCardBody = (card: (typeof cards)[number]) => (
    <>
      <span className={`${card.highlight ? "text-xs" : "text-xs"} ${mutedText(theme)} uppercase tracking-wider flex items-center gap-1 mb-2`}>
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

  // Two-tier layout so a first-time viewer has an obvious "start here": the
  // hero tile plus the other highlight tiles render first, larger and with
  // their own section label; everything else follows under a plainer
  // "More Detail" label. Purely a render-order/label split of the same
  // `cards` data above -- no values, order-of-computation, or logic changed.
  const heroCards = cards.map((card, idx) => ({ card, idx })).filter(({ card }) => card.highlight);
  const detailCards = cards.map((card, idx) => ({ card, idx })).filter(({ card }) => !card.highlight);

  return (
    <div className="space-y-6">
      <div className={`${glassCard(theme)} p-4 flex flex-wrap items-center justify-between gap-3`}>
        <span className={`text-sm font-mono ${isDark ? "text-zinc-100" : "text-zinc-800"}`}>
          <span className="mr-2" aria-hidden="true">{verdict.emoji}</span>
          {verdict.text}
        </span>
        {verdict.actionLabel && verdict.onAction && (
          <button
            type="button"
            onClick={verdict.onAction}
            className="text-sm font-mono font-semibold whitespace-nowrap hover:underline shrink-0"
            style={{ color: accent }}
          >
            {verdict.actionLabel}
          </button>
        )}
      </div>

      <div className="space-y-3">
        <span className={`text-xs font-mono uppercase tracking-wider block ${mutedText(theme)}`}>At a Glance</span>
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 font-mono">
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
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-5 font-mono">
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
              <p className={sectionTextClass(isDark)}>
                {activeClientName}'s reputation is {scoreDisplay} ({gradeDisplay}), trending {trendDisplay}.
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark, true)}>
                Risk Profile
                <InfoTooltip label="About Average Risk Score"><AverageRiskScoreTrackedDefinition /></InfoTooltip>
              </span>
              <p className={sectionTextClass(isDark)}>
                {riskStats.total} risks are being tracked ({riskStats.critical} critical, {riskStats.high} high, {riskStats.medium} medium, {riskStats.low} low), with an average risk score of{" "}
                <button type="button" onClick={() => navigateTo("risk")} className="hover:underline font-bold">{riskStats.avg}</button>.
                {riskStats.topRiskDocs.length > 0 && (
                  <>
                    {" "}The highest-risk item is "{riskStats.topRiskDocs[0].title}" ({riskStats.topRiskDocs[0].risk.toFixed(1)} pts)
                    {riskStats.topRiskDocs[1] ? `, followed by "${riskStats.topRiskDocs[1].title}" (${riskStats.topRiskDocs[1].risk.toFixed(1)} pts).` : "."}
                  </>
                )}
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark, true)}>
                Sentiment
                <InfoTooltip label="About Positive Signals & Dominant Sentiment"><EntitySentimentSplitDefinition /></InfoTooltip>
              </span>
              <p className={sectionTextClass(isDark)}>
                Sentiment is running {sentiment.dominant ?? "unknown"} across this client's own entity mentions ({sentiment.positive} positive / {sentiment.neutral} neutral / {sentiment.negative} negative mentions — see Executive Analytics for the document-level Sentiment Breakdown).
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Notable People in Coverage</span>
              <p className={sectionTextClass(isDark)}>
                {execStats.mostMentioned
                  ? <>{execStats.mostMentioned} is the most-mentioned person, out of {execStats.total} notable people tracked in {activeClientName}'s coverage (not necessarily {activeClientName}'s own staff).</>
                  : <>No notable people have been tracked yet in {activeClientName}'s coverage.</>}
                {execStats.highest && execStats.lowest && execStats.highest !== execStats.lowest && (
                  <> {execStats.highest.name} has the highest sentiment score in this coverage ({(execStats.highest.score ?? 0).toFixed(1)}), while {execStats.lowest.name} has the lowest ({(execStats.lowest.score ?? 0).toFixed(1)}).</>
                )}
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Competitive Standing</span>
              <p className={sectionTextClass(isDark)}>
                {activeClientName} ranks {clientRank} among competitors found in coverage with {sovDisplay}% share of voice (a separate, passive signal from Competitor Compare's opt-in tracking list).
                {topCompetitor && <> The top-ranked competitor is {topCompetitor.competitor_name}.</>}
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Alerts</span>
              <p className={sectionTextClass(isDark)}>{alertLine}</p>
            </div>
        </CardContent>
      </Card>

      <Card className={glassCard(theme)} ref={whatToDoRef}>
        <div className={SPECULAR_LINE} />
        <CardContent className="p-4 space-y-2">
          <span className={sectionLabelClass(isDark)}>What to do about it</span>
          {planAdvisoryLoading ? (
            <p className={`text-sm leading-relaxed font-mono mt-1.5 ${isDark ? "text-zinc-300" : "text-zinc-600"}`}>Analyzing current risk posture...</p>
          ) : planAdvisoryError ? (
            <p className={`text-sm leading-relaxed font-mono mt-1.5 ${isDark ? "text-zinc-300" : "text-zinc-600"}`}>Advisory temporarily unavailable.</p>
          ) : planAdvisory?.lead ? (
            <>
              <p className={`text-sm leading-relaxed font-mono mt-1.5 ${isDark ? "text-zinc-200" : "text-zinc-700"}`}>{planAdvisory.lead}</p>
              {Array.isArray(planAdvisory.bullets) && planAdvisory.bullets.length > 0 && (
                <ul className="space-y-1.5 mt-2">
                  {planAdvisory.bullets.map((b: string, idx: number) => (
                    <li key={idx} className={`text-sm leading-relaxed font-mono flex gap-2 ${isDark ? "text-zinc-300" : "text-zinc-600"}`}>
                      <span className="shrink-0" style={{ color: accent }}>&#8226;</span>
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className={`text-sm leading-relaxed font-mono mt-1.5 ${isDark ? "text-zinc-300" : "text-zinc-600"}`}>
              Nothing significant to flag right now — actively watching {riskStats.total} tracked risk{riskStats.total === 1 ? "" : "s"} for {activeClientName}. You'll see a recommendation here the moment something needs attention.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
