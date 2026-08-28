import React, { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { getRiskLevel } from "@/utils/riskLevel";
import { ResponsiveContainer, AreaChart, Area, Tooltip } from "recharts";

export interface ReputationSummaryCardProps {
  reputationSummaryLoading: boolean;
  reputationSummaryError: string | null;
  reputationSummary: any;
  documents: any[];
  narratives: any[];
  executives: any[];
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

// Same gold small-caps section header / body text styling as the Narrative
// Registry's "AI Executive Summary" block (NarrativeIntelligenceWorkbench.tsx
// lines 352-359) -- that block is a plain template-literal string, not an
// LLM call, so this panel's text stays deterministic/template-based too.
const SECTION_LABEL_CLASS = "text-[9.5px] text-[#D4AF37] font-bold uppercase tracking-wider block border-b border-[#1F2937]/30 pb-1";
const SECTION_TEXT_CLASS = "text-[11px] text-slate-300 leading-relaxed font-mono mt-1.5";

// SOV bands considered notably low/high for the Key Highlights bullet.
const SOV_LOW_THRESHOLD = 15;
const SOV_HIGH_THRESHOLD = 40;
// Same "EXPANDING" velocity threshold as the Narrative Registry's Velocity
// Index badge (NarrativeIntelligenceWorkbench.tsx line 374).
const VELOCITY_FLAG_THRESHOLD = 15;

export function ReputationSummaryCard({
  reputationSummaryLoading,
  reputationSummaryError,
  reputationSummary,
  documents = [],
  narratives = [],
  executives = [],
  clientRank,
  clientSOV,
  activeClientName,
  normalizedBenchmarks = [],
  repHistory = [],
}: ReputationSummaryCardProps) {
  // Total risks + severity breakdown + avg risk score, same computation as
  // Risk Center's stat cards (RiskTab.tsx `stats`), driven off documents.
  const riskStats = useMemo(() => {
    const riskDocs = (documents || []).filter(d => d && typeof d.risk === "number");
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
    // just showing a count.
    const topRiskDocs = [...riskDocs].sort((a, b) => (b.risk || 0) - (a.risk || 0)).slice(0, 2);
    return { total, critical, high, medium, low, avg, dominantLevel, dangerCount: critical + high, topRiskDocs };
  }, [documents]);

  // Highest risk / fastest growing narrative + monitored count, same
  // computation as Narrative Cluster's stat cards (NarrativesTab.tsx `summaryKpis`).
  const narrativeStats = useMemo(() => {
    const sortedByRisk = [...narratives].sort((a, b) => (b.risk || 0) - (a.risk || 0));
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
            <div key={i} className="h-24 bg-[#060B18]/60 border border-[#1F2937]/60 rounded-lg" />
          ))}
        </div>
        <div className="h-20 bg-[#060B18]/60 border border-[#1F2937]/60 rounded-lg" />
      </div>
    );
  }

  if (reputationSummaryError || !reputationSummary) {
    return (
      <Card className="bg-[#060B18]/60 border-red-500/20 h-32">
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

  const cards = [
    { label: "Reputation Score", value: scoreDisplay, sub: scoreKnown ? `Grade ${gradeDisplay}` : "", color: "text-[#D4AF37]", highlight: true },
    { label: "Risk Signals", value: riskStats.dangerCount, sub: "Critical + High", color: riskStats.dangerCount > 0 ? "text-red-500" : "text-emerald-500", highlight: true },
    { label: "Trend Direction", value: trendDisplay, sub: "Reputation momentum", color: "text-purple-400", highlight: true, compactValue: true },
    { label: "Total Risks Tracked", value: riskStats.total, sub: `${riskStats.critical}C/${riskStats.high}H/${riskStats.medium}M/${riskStats.low}L`, color: RISK_COLOR[riskStats.dominantLevel] },
    { label: "Positive Signals", value: sentiment.positive, sub: "Positive-sentiment docs", color: "text-emerald-400" },
    { label: "Dominant Sentiment", value: sentiment.dominant ?? "N/A", sub: `${sentiment.positive}/${sentiment.neutral}/${sentiment.negative}`, color: "text-emerald-400" },
    { label: "Narratives Monitored", value: narrativeStats.total, sub: "Active media clusters", color: "text-[#D4AF37]" },
    { label: "Highest Risk Narrative", value: narrativeStats.highestRisk, sub: "Requires strategic review", color: "text-red-500" },
    { label: "Fastest Growing Narrative", value: narrativeStats.fastestGrowing, sub: "High velocity trend", color: "text-orange-400" },
    { label: "Most Mentioned Executive", value: execStats.mostMentioned, sub: "Core voice proxy", color: "text-indigo-400" },
    { label: "Tracked Executives", value: execStats.total, sub: "Monitored corporate heads", color: "text-[#38BDF8]" },
    { label: "Competitor Rank / SOV", value: clientRank, sub: `${sovDisplay}% SOV`, color: "text-[#38BDF8]" },
    { label: "Executive Alerts", value: execAlert.open ? 1 : 0, sub: execAlert.open ? (alertNames ?? "Open alert") : "None open", color: execAlert.open ? "text-red-500" : "text-emerald-500" },
  ];

  // Deterministic, threshold-driven bullets -- same idea as the reference
  // panel's "Action Recommendations", kept to 2-4 and only the ones that apply.
  const highlights: string[] = [];
  if (riskStats.dangerCount > 0) {
    highlights.push(`${riskStats.dangerCount} critical/high risk${riskStats.dangerCount === 1 ? "" : "s"} require review${riskStats.topRiskDocs[0] ? ` (top: "${riskStats.topRiskDocs[0].title}")` : ""}.`);
  }
  if (execAlert.open) {
    highlights.push(`Open executive-risk alert on ${alertNames ?? "an unnamed executive"} needs attention.`);
  }
  if (narrativeStats.fastestGrowingTrend !== undefined && narrativeStats.fastestGrowingTrend >= VELOCITY_FLAG_THRESHOLD) {
    highlights.push(`"${narrativeStats.fastestGrowing}" is expanding fast (+${narrativeStats.fastestGrowingTrend.toFixed(1)}% velocity) -- monitor closely.`);
  }
  if (clientSOV > 0 && (clientSOV < SOV_LOW_THRESHOLD || clientSOV > SOV_HIGH_THRESHOLD)) {
    highlights.push(
      clientSOV < SOV_LOW_THRESHOLD
        ? `Share of voice is notably low at ${sovDisplay}%${topCompetitor ? ` versus leader ${topCompetitor.competitor_name}` : ""}.`
        : `Share of voice is notably strong at ${sovDisplay}%, leading the tracked competitor set.`
    );
  }
  const shownHighlights = highlights.slice(0, 4);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-8 font-mono">
        {cards.map((card, idx) => (
          <div
            key={idx}
            className={`bg-[#060B18]/60 border rounded-lg p-4 flex flex-col justify-between shadow-[0_0_12px_rgba(212,175,55,0.06)] hover:shadow-[0_0_16px_rgba(212,175,55,0.18)] transition-all duration-300 ${
              card.highlight
                ? "border-[#D4AF37] shadow-[0_0_18px_rgba(212,175,55,0.14)] md:col-span-2 lg:col-span-2"
                : "border-[#D4AF37]/40 hover:border-[#D4AF37]"
            }`}
          >
            <span className={`${card.highlight ? "text-[10px]" : "text-[9px]"} text-slate-500 uppercase tracking-wider block mb-2`}>{card.label}</span>
            <div>
              <span className={`${card.highlight && !card.compactValue ? "text-2xl" : "text-xl"} font-bold block truncate ${card.color}`}>{card.value}</span>
              {card.sub && <span className="text-[9px] text-slate-500 block truncate mt-1">{card.sub}</span>}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 bg-[#060B18]/60 border-[#D4AF37]/40 shadow-[0_0_16px_rgba(212,175,55,0.08)]">
          <CardContent className="p-4 space-y-4">
            <div>
              <span className={SECTION_LABEL_CLASS}>Overview</span>
              <p className={SECTION_TEXT_CLASS}>
                {activeClientName}'s reputation is {scoreDisplay} ({gradeDisplay}), trending {trendDisplay}.
              </p>
            </div>

            <div>
              <span className={SECTION_LABEL_CLASS}>Risk Profile</span>
              <p className={SECTION_TEXT_CLASS}>
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
              <span className={SECTION_LABEL_CLASS}>Sentiment</span>
              <p className={SECTION_TEXT_CLASS}>
                Sentiment is running {sentiment.dominant ?? "unknown"} ({sentiment.positive} positive / {sentiment.neutral} neutral / {sentiment.negative} negative).
                {drivingTheme && <> The leading driver is the "{drivingTheme.name}" narrative ({drivingTheme.sentiment.toFixed(2)} sentiment).</>}
              </p>
            </div>

            <div>
              <span className={SECTION_LABEL_CLASS}>Narrative Landscape</span>
              <p className={SECTION_TEXT_CLASS}>
                {narrativeStats.total} narrative{narrativeStats.total === 1 ? "" : "s"} are being monitored. The highest-risk narrative is "{narrativeStats.highestRisk}"{typeof narrativeStats.highestRiskScore === "number" ? ` (Risk Index ${narrativeStats.highestRiskScore.toFixed(1)} pts)` : ""}. The fastest-growing narrative is "{narrativeStats.fastestGrowing}"{typeof narrativeStats.fastestGrowingTrend === "number" ? ` (Velocity Index ${narrativeStats.fastestGrowingTrend >= 0 ? "+" : ""}${narrativeStats.fastestGrowingTrend.toFixed(1)}%)` : ""}.
              </p>
            </div>

            <div>
              <span className={SECTION_LABEL_CLASS}>Leadership</span>
              <p className={SECTION_TEXT_CLASS}>
                {execStats.mostMentioned} is the most-mentioned executive, out of {execStats.total} tracked executive{execStats.total === 1 ? "" : "s"}.
                {execStats.highest && execStats.lowest && execStats.highest !== execStats.lowest && (
                  <> {execStats.highest.name} leads on reputation ({(execStats.highest.score ?? 0).toFixed(1)}), while {execStats.lowest.name} trails ({(execStats.lowest.score ?? 0).toFixed(1)}).</>
                )}
              </p>
            </div>

            <div>
              <span className={SECTION_LABEL_CLASS}>Competitive Standing</span>
              <p className={SECTION_TEXT_CLASS}>
                {activeClientName} ranks {clientRank} among tracked competitors with {sovDisplay}% share of voice.
                {topCompetitor && <> The top-ranked competitor is {topCompetitor.competitor_name}.</>}
              </p>
            </div>

            <div>
              <span className={SECTION_LABEL_CLASS}>Alerts</span>
              <p className={SECTION_TEXT_CLASS}>{alertLine}</p>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          {repHistory.length > 0 && (
            <Card className="bg-[#060B18]/60 border-[#D4AF37]/40 shadow-[0_0_16px_rgba(212,175,55,0.08)]">
              <CardContent className="p-4">
                <span className="text-[9.5px] text-[#D4AF37] font-bold uppercase tracking-wider block mb-2">Reputation Trend</span>
                <div className="h-20 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={repHistory}>
                      <defs>
                        <linearGradient id="repTrendGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#D4AF37" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#D4AF37" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Tooltip contentStyle={{ backgroundColor: "#060B18", borderColor: "#1F2937", color: "#fff", fontSize: 10 }} />
                      <Area type="monotone" dataKey="score" stroke="#D4AF37" strokeWidth={1.5} fillOpacity={1} fill="url(#repTrendGradient)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}

          <Card className="bg-[#060B18]/60 border-[#D4AF37]/40 shadow-[0_0_16px_rgba(212,175,55,0.08)]">
            <CardContent className="p-4 space-y-2">
              <span className={SECTION_LABEL_CLASS}>Key Highlights</span>
              {shownHighlights.length > 0 ? (
                <ul className="space-y-2 mt-1.5">
                  {shownHighlights.map((h, idx) => (
                    <li key={idx} className="text-[11px] text-slate-300 leading-relaxed font-mono flex gap-2">
                      <span className="text-[#D4AF37] shrink-0">&#8226;</span>
                      <span>{h}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className={SECTION_TEXT_CLASS}>No thresholds breached -- reputation posture is stable.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
