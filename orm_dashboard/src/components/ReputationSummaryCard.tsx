import React, { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { getRiskLevel, RISK_THRESHOLDS } from "@/utils/riskLevel";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, mutedText, bodyText, GRADIENT_HEADING_CLASS, gradientHeadingStyle, SPECULAR_LINE } from "@/components/theme/tokens";
import { HeroGlass } from "@/components/theme/HeroGlass";

export interface ReputationSummaryCardProps {
  reputationSummaryLoading: boolean;
  reputationSummaryError: string | null;
  reputationSummary: any;
  planAdvisory?: any;
  planAdvisoryLoading?: boolean;
  planAdvisoryError?: string | null;
  onViewNarrative?: (narrativeName: string) => void;
  documents: any[];
  documentsLoading?: boolean;
  narratives: any[];
  narrativesLoading?: boolean;
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

// Same small-caps section header / body text styling as the Narrative
// Registry's "AI Executive Summary" block (NarrativeIntelligenceWorkbench.tsx
// lines 352-359) -- that block is a plain template-literal string, not an
// LLM call, so this panel's text stays deterministic/template-based too.
// Theme-aware functions instead of static strings since the accent + border
// now depend on light/dark glass mode.
function sectionLabelClass(isDark: boolean) {
  return `text-xs font-bold uppercase tracking-wider block border-b pb-1 ${
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
  onViewNarrative,
  documents = [],
  documentsLoading = false,
  narratives = [],
  narrativesLoading = false,
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

  // Highest risk / fastest growing narrative + monitored count, same
  // computation as Narrative Cluster's stat cards (NarrativesTab.tsx `summaryKpis`).
  const narrativeStats = useMemo(() => {
    // Requires MEDIUM+ (same RISK_THRESHOLDS.LOW_TO_MEDIUM floor as
    // riskStats.topRiskDocs above) -- without it, "highest risk narrative"
    // just meant "whichever narrative scored the most, even 0", which
    // could name a trivial or entirely risk-free narrative as one
    // "requiring strategic review".
    const riskyNarratives = narratives.filter(n => (n.risk || 0) > RISK_THRESHOLDS.LOW_TO_MEDIUM);
    const sortedByRisk = [...riskyNarratives].sort((a, b) => (b.risk || 0) - (a.risk || 0));
    const sortedByTrend = [...narratives].sort((a, b) => (b.trend || 0) - (a.trend || 0));
    const highest = sortedByRisk[0] || null;
    const fastest = sortedByTrend[0] || null;
    return {
      total: narratives.length,
      highestRisk: highest?.name || "None Detected",
      highestRiskScore: highest?.risk,
      fastestGrowing: fastest?.name || "None Detected",
      fastestGrowingTrend: fastest?.trend,
    };
  }, [narratives]);

  // Most mentioned executive + tracked leaders count, same computation as
  // NarrativesTab.tsx `summaryKpis`. Highest/lowest scoring executive uses
  // the same `.score` field and `?? 0` fallback as ExecutivesTab's summary
  // memo (ExecutivesTab.tsx lines 97-99).
  const execStats = useMemo(() => {
    const mostMentioned = [...executives].sort((a, b) => (b.mention_count || 0) - (a.mention_count || 0))[0]?.name || "None Detected";
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

  // Dominant sentiment "driving theme": the narrative whose own sentiment
  // sign matches the platform-wide dominant sentiment, picked by largest
  // magnitude -- reuses the `narratives[].sentiment` field already powering
  // the Narrative Registry, no new computation. Computed here (ahead of the
  // loading/error early-returns below) so hook call order stays constant
  // across renders; falls back to null when summary data isn't loaded yet.
  const dominantSentiment: string | null = reputationSummary?.sentiment?.dominant ?? null;
  const drivingTheme = useMemo(() => {
    if (!dominantSentiment || (dominantSentiment !== "positive" && dominantSentiment !== "negative")) return null;
    const wantPositive = dominantSentiment === "positive";
    const candidates = (narratives || []).filter(n =>
      typeof n.sentiment === "number" && (wantPositive ? n.sentiment > 0 : n.sentiment < 0)
    );
    if (candidates.length === 0) return null;
    candidates.sort((a, b) => Math.abs(b.sentiment) - Math.abs(a.sentiment));
    return candidates[0];
  }, [narratives, dominantSentiment]);

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
  const scoreDisplay = scoreKnown ? rep.score.toFixed(1) : "N/A";
  const gradeDisplay = scoreKnown ? (rep.grade ?? "N/A") : "N/A";
  const trendDisplay = rep.trend ?? "STABLE";
  const sovDisplay = clientSOV.toFixed(1);

  const alertNames = execAlert.open && execAlert.alert?.entity_name ? execAlert.alert.entity_name : null;
  const alertLine = execAlert.open
    ? `1 open executive-risk alert: ${alertNames ?? "unknown"}.`
    : "No open executive-risk alerts.";

  // documents/narratives/executives each load independently and can settle
  // at noticeably different times after a client switch (confirmed live:
  // reputationSummary -- which sentiment reads from -- lands well before
  // documents does), so a card computed off a still-loading source showed a
  // real "0 risks tracked" next to an already-correct, non-zero reputation
  // score for several real seconds -- a genuine, reproducible transient
  // misread risk, not a one-off glitch. "—" while loading is honest;
  // rendering the real zero before the real data has arrived is not.
  const LOADING_PLACEHOLDER = "—";
  const cards = [
    { label: "Reputation Score", value: scoreDisplay, sub: scoreKnown ? `Grade ${gradeDisplay}` : "", color: "text-[#D4AF37]", highlight: true },
    { label: "Risk Signals", value: documentsLoading ? LOADING_PLACEHOLDER : riskStats.dangerCount, sub: "Critical + High", color: riskStats.dangerCount > 0 ? "text-red-500" : "text-emerald-500", highlight: true },
    { label: "Trend Direction", value: trendDisplay, sub: "Reputation momentum", color: "text-sky-500", highlight: true, compactValue: true },
    { label: "Total Risks Tracked", value: documentsLoading ? LOADING_PLACEHOLDER : riskStats.total, sub: documentsLoading ? "Loading..." : `${riskStats.critical}C/${riskStats.high}H/${riskStats.medium}M/${riskStats.low}L`, color: RISK_COLOR[riskStats.dominantLevel] },
    { label: "Positive Signals", value: sentiment.positive, sub: "Positive-sentiment docs", color: "text-emerald-400" },
    { label: "Dominant Sentiment", value: sentiment.dominant ?? "N/A", sub: `${sentiment.positive}/${sentiment.neutral}/${sentiment.negative}`, color: "text-emerald-400" },
    { label: "Narratives Monitored", value: narrativesLoading ? LOADING_PLACEHOLDER : narrativeStats.total, sub: "Active media clusters", color: "text-sky-500" },
    { label: "Highest Risk Narrative", value: narrativesLoading ? LOADING_PLACEHOLDER : narrativeStats.highestRisk, sub: "Requires strategic review", color: "text-red-500" },
    { label: "Fastest Growing Narrative", value: narrativesLoading ? LOADING_PLACEHOLDER : narrativeStats.fastestGrowing, sub: "High velocity trend", color: "text-orange-400" },
    { label: "Most Mentioned Executive", value: executivesLoading ? LOADING_PLACEHOLDER : execStats.mostMentioned, sub: "Overall visibility", color: "text-sky-500" },
    { label: "Tracked Executives", value: executivesLoading ? LOADING_PLACEHOLDER : execStats.total, sub: "Monitored leaders", color: "text-sky-500" },
    { label: "Competitor Rank / Share of Voice", value: clientRank, sub: `${sovDisplay}% share of voice`, color: "text-sky-500" },
    { label: "Executive Alerts", value: execAlert.open ? 1 : 0, sub: execAlert.open ? (alertNames ?? "Open alert") : "None open", color: execAlert.open ? "text-red-500" : "text-emerald-500" },
  ];

  // Only the Reputation Score tile (index 0 -- the single number this whole
  // panel exists to surface) gets the full spotlight + border-beam glass
  // treatment. Everything else, including the other "highlight" tiles, gets
  // the plain glass-card base style -- see the redesign report for why.
  const statCardBody = (card: (typeof cards)[number]) => (
    <>
      <span className={`${card.highlight ? "text-xs" : "text-xs"} ${mutedText(theme)} uppercase tracking-wider block mb-2`}>{card.label}</span>
      <div>
        <span className={`${card.highlight && !card.compactValue ? "text-2xl" : "text-xl"} font-bold block truncate ${card.color}`}>{card.value}</span>
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
      <div className="space-y-3">
        <span className={`text-xs font-mono uppercase tracking-wider block ${mutedText(theme)}`}>At a Glance</span>
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 font-mono">
          {heroCards.map(({ card, idx }) =>
            idx === 0 ? (
              <HeroGlass key={idx} theme={theme} className="p-4 flex flex-col justify-between">
                {statCardBody(card)}
              </HeroGlass>
            ) : (
              <div key={idx} className={`${glassCard(theme)} p-4 flex flex-col justify-between`}>
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
            <div key={idx} className={`${glassCard(theme)} p-4 flex flex-col justify-between`}>
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
              <span className={sectionLabelClass(isDark)}>Risk Profile</span>
              <p className={sectionTextClass(isDark)}>
                {riskStats.total} risks are being tracked ({riskStats.critical} critical, {riskStats.high} high, {riskStats.medium} medium, {riskStats.low} low), with an average risk score of {riskStats.avg}.
                {riskStats.topRiskDocs.length > 0 && (
                  <>
                    {" "}The highest-risk item is "{riskStats.topRiskDocs[0].title}" ({riskStats.topRiskDocs[0].risk.toFixed(1)} pts)
                    {riskStats.topRiskDocs[1] ? `, followed by "${riskStats.topRiskDocs[1].title}" (${riskStats.topRiskDocs[1].risk.toFixed(1)} pts).` : "."}
                  </>
                )}
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Sentiment</span>
              <p className={sectionTextClass(isDark)}>
                Sentiment is running {sentiment.dominant ?? "unknown"} ({sentiment.positive} positive / {sentiment.neutral} neutral / {sentiment.negative} negative).
                {drivingTheme && <> The leading driver is the "{drivingTheme.name}" narrative ({drivingTheme.sentiment.toFixed(2)} sentiment).</>}
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Narrative Landscape</span>
              <p className={sectionTextClass(isDark)}>
                {narrativeStats.total} narrative{narrativeStats.total === 1 ? "" : "s"} are being monitored. The highest-risk narrative is "{narrativeStats.highestRisk}"{typeof narrativeStats.highestRiskScore === "number" ? ` (Risk Score ${narrativeStats.highestRiskScore.toFixed(1)} pts)` : ""}. The fastest-growing narrative is "{narrativeStats.fastestGrowing}"{typeof narrativeStats.fastestGrowingTrend === "number" ? ` (Coverage Trend ${narrativeStats.fastestGrowingTrend >= 0 ? "+" : ""}${narrativeStats.fastestGrowingTrend.toFixed(1)}%)` : ""}.
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Leadership</span>
              <p className={sectionTextClass(isDark)}>
                {execStats.mostMentioned} is the most-mentioned executive, out of {execStats.total} tracked executive{execStats.total === 1 ? "" : "s"}.
                {execStats.highest && execStats.lowest && execStats.highest !== execStats.lowest && (
                  <> {execStats.highest.name} leads on reputation ({(execStats.highest.score ?? 0).toFixed(1)}), while {execStats.lowest.name} trails ({(execStats.lowest.score ?? 0).toFixed(1)}).</>
                )}
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Competitive Standing</span>
              <p className={sectionTextClass(isDark)}>
                {activeClientName} ranks {clientRank} among tracked competitors with {sovDisplay}% share of voice.
                {topCompetitor && <> The top-ranked competitor is {topCompetitor.competitor_name}.</>}
              </p>
            </div>

            <div>
              <span className={sectionLabelClass(isDark)}>Alerts</span>
              <p className={sectionTextClass(isDark)}>{alertLine}</p>
            </div>
        </CardContent>
      </Card>

      <Card className={glassCard(theme)}>
        <div className={SPECULAR_LINE} />
        <CardContent className="p-4 space-y-2">
          <span className={sectionLabelClass(isDark)}>AI Advisory</span>
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
              {planAdvisory.top_narrative_name && onViewNarrative && (
                <button
                  type="button"
                  onClick={() => onViewNarrative(planAdvisory.top_narrative_name)}
                  className="flex items-center min-h-[44px] text-sm font-mono font-semibold mt-2 hover:underline"
                  style={{ color: accent }}
                >
                  View full narrative &rarr;
                </button>
              )}
            </>
          ) : (
            <p className={`text-sm leading-relaxed font-mono mt-1.5 ${isDark ? "text-zinc-300" : "text-zinc-600"}`}>Nothing significant to flag right now.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
