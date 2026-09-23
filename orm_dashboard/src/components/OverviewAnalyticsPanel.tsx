import React, { useMemo } from "react";
import { BarChart3, LineChart, Activity, Smile, TrendingUp, HelpCircle } from "lucide-react";
import { 
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, CartesianGrid, XAxis, YAxis,
  LineChart as RechartsLineChart, Line
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, mutedText, SPECULAR_LINE } from "@/components/theme/tokens";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { ReputationScoreDefinition, SentimentScaleDefinition, CoverageByTopicDefinition, OverviewSentimentBreakdownDefinition, AverageSentimentTrendDefinition } from "@/lib/metricDefinitions";
import { formatScore, tooltipScoreFormatter } from "@/utils/formatScore";

export interface OverviewAnalyticsPanelProps {
  sentimentDistData: any[];
  topicDistData: any[];
  repHistory: any[];
  sentimentTrendData: any[];
  loading?: boolean;
  error?: string | null;
}

export function OverviewAnalyticsPanel({
  sentimentDistData = [],
  topicDistData = [],
  repHistory = [],
  sentimentTrendData = [],
  loading = false,
  error = null
}: OverviewAnalyticsPanelProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const accentColor = isDark ? "text-[#00F5D4]" : "text-[#3B82F6]";
  // 1. KPI Summaries based on live prop telemetry
  const kpis = useMemo(() => {
    // repHistory arrives already reversed into chronological (oldest-first)
    // order for the trend chart below (see useDashboardData.ts's
    // fetchReputationHistory handler) -- the latest point is the LAST
    // entry, not the first. Reading repHistory[0] here was silently
    // surfacing the oldest score in the last-30-days window as if it were
    // current (xoop_ui_clarity_review.md Phase 1: this is what produced
    // "AVG REPUTATION: 76.32" here vs. the dashboard's correct, current
    // "REPUTATION SCORE: 60.06" for the same client at the same time --
    // same metric, not two different ones, just the wrong end of a reversed
    // array). Also relabeled below: this was never an average, it's a
    // single point-in-time score, same as the dashboard's own tile.
    const latestRep = repHistory.length > 0 ? repHistory[repHistory.length - 1].score : 0;
    const latestRepScore = latestRep > 0 ? latestRep.toFixed(2) : "0.00";
    
    const dimensionsCount = topicDistData.length;

    const posVal = sentimentDistData.find(d => d.name === "Positive")?.value || 0;
    const totalVal = sentimentDistData.reduce((acc, curr) => acc + (curr.value || 0), 0);
    const posRatio = totalVal > 0 ? `${((posVal / totalVal) * 100).toFixed(0)}%` : "0%";

    // Derived from the exact same Positive/Neutral/Negative counts that
    // feed the Sentiment Breakdown donut below (sentimentDistData), not a
    // separate query or the trend chart's single latest bucket -- tile and
    // donut can now never visibly disagree, since they're the same numbers.
    // Weighting matches the backend's own convention (sentiment_analyzer.py
    // score_map: positive=1.0, neutral=0.0, negative=-1.0, see
    // metricDefinitions.tsx's Sentiment scale note) rather than inventing a
    // new one.
    const negVal = sentimentDistData.find(d => d.name === "Negative")?.value || 0;
    // Same "too few to trust" floor risk_engine.py already uses for trend
    // significance (risk_engine.py:790,796), reused here rather than picking
    // a new threshold in isolation.
    const SENTIMENT_SCORE_MIN_SAMPLE = 5;
    const hasEnoughSentimentData = totalVal >= SENTIMENT_SCORE_MIN_SAMPLE;
    const sentimentScoreValue = hasEnoughSentimentData ? (posVal - negVal) / totalVal : null;
    const latestSentScore = sentimentScoreValue === null
      ? "Not enough data yet"
      : sentimentScoreValue > 0
      ? `+${sentimentScoreValue.toFixed(2)}`
      : sentimentScoreValue.toFixed(2);

    return [
      { label: "Current Reputation", value: latestRepScore, desc: "Overall reputation score", icon: Activity, color: accentColor, def: <ReputationScoreDefinition /> },
      { label: "Sentiment Score", value: latestSentScore, desc: hasEnoughSentimentData ? "How positive coverage is (-1.0 to +1.0)" : "Awaiting more coverage to compute", icon: Smile, color: accentColor, def: <SentimentScaleDefinition /> },
      { label: "Topics Covered", value: dimensionsCount, desc: "Distinct topics found in coverage", icon: BarChart3, color: "text-purple-400", def: undefined as React.ReactNode },
      { label: "Positive Share", value: posRatio, desc: "Favorable media percentage", icon: TrendingUp, color: "text-emerald-400", def: undefined as React.ReactNode }
    ];
  }, [repHistory, topicDistData, sentimentDistData, accentColor]);

  const tooltipStyle = {
    backgroundColor: isDark ? 'rgba(24, 24, 27, 0.95)' : 'rgba(255, 255, 255, 0.95)',
    borderColor: isDark ? '#3f3f46' : '#e4e4e7',
    borderRadius: '8px',
    boxShadow: isDark ? '0 10px 30px rgba(0, 0, 0, 0.8)' : '0 10px 30px rgba(0, 0, 0, 0.1)',
    color: isDark ? '#e4e4e7' : '#18181b',
    fontFamily: 'monospace',
    fontSize: '11px',
    padding: '12px'
  };

  const cardStyle = `${glassCard(theme)} hover:-translate-y-0.5`;
  const gridStroke = isDark ? "#3f3f46" : "#d4d4d8";
  const axisStroke = isDark ? "#a1a1aa" : "#71717a";

  // Hover explanation for the sentiment trend. Narrative clustering was
  // removed from the pipeline (2026-09-19) -- this used to also surface a
  // per-day "driving narrative" root-cause excerpt sourced from that
  // feature, but with narratives never generating, that branch could never
  // fire (its data source was permanently empty) and always fell through
  // to a generic message anyway. Simplified to just the honest states this
  // chart can actually support: a meaningful move with no note, or normal
  // day-to-day fluctuation.
  const SentimentTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || !payload.length) return null;
    const point = payload[0].payload;
    return (
      <div style={tooltipStyle} className="space-y-1 max-w-[260px]">
        <div className="font-bold">{label}</div>
        <div>Sentiment: {point.Sentiment >= 0 ? "+" : ""}{formatScore(point.Sentiment, 2)}</div>
        {point.meaningful ? (
          <div className="pt-1 border-t border-current/10 text-[10px] italic opacity-70">
            Sentiment moved but no specific narrative or risk event is linked to it in the data.
          </div>
        ) : (
          <div className="pt-1 border-t border-current/10 text-[10px] italic opacity-70">
            Normal day-to-day fluctuation — nothing significant to flag.
          </div>
        )}
      </div>
    );
  };

  const SentimentDot = (props: any) => {
    const { cx, cy } = props;
    if (cx === undefined || cy === undefined) return null;
    return (
      <circle
        cx={cx}
        cy={cy}
        r={3.5}
        stroke={accent}
        strokeWidth={1.5}
        fill={isDark ? "#09090b" : "#ffffff"}
      />
    );
  };

  if (loading) {
    return (
      <div className="grid gap-6 md:grid-cols-2 animate-pulse">
        {[1, 2, 3, 4].map(x => (
          <div key={x} className={`h-[300px] rounded-3xl ${glassTokens[theme].card}`} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Card className={`${glassCard(theme)} border-red-500/20 h-96`}>
        <TelemetryErrorWidget title="Overview Telemetry Offline" message={error} />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI summaries header */}
      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-4 font-mono">
        {kpis.map((k, idx) => {
          const Icon = k.icon;
          return (
            <div
              key={idx}
              className={`${glassCard(theme)} p-4 flex flex-col justify-between`}
            >
              <div className={SPECULAR_LINE} />
              <div className="flex justify-between items-start mb-2">
                <span className={`text-xs uppercase tracking-wider flex items-center gap-1 ${mutedText(theme)}`}>
                  {k.label}
                  {k.def && <InfoTooltip label={`About ${k.label}`}>{k.def}</InfoTooltip>}
                </span>
                <Icon className={`h-4 w-4 ${k.color}`} />
              </div>
              <div>
                <span className={`text-xl font-bold block ${k.color}`}>{k.value}</span>
                <span className={`text-xs ${mutedText(theme)}`}>{k.desc}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Sentiment Distribution */}
        <Card className={cardStyle}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center ${mutedText(theme)}`}>
              Sentiment Breakdown
              <InfoTooltip label="About Sentiment Breakdown"><OverviewSentimentBreakdownDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="h-[260px]">
            {sentimentDistData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sentimentDistData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    // Recharts 3.8.1 + React 19: the Pie entrance animation
                    // reliably left the sector <path> elements empty on
                    // this stack (confirmed live: sectors present in the
                    // DOM, laid out, zero pixels painted). Disabling the
                    // animation is the standard workaround for this pairing
                    // (xoop_ui_clarity_review.md "Sentiment Breakdown"
                    // blank-card bug).
                    isAnimationActive={false}
                  >
                    {sentimentDistData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full space-y-2">
                <BarChart3 className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
                <p className={`font-mono text-xs ${mutedText(theme)}`}>No sentiment distribution data.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Topic Frequency */}
        <Card className={cardStyle}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center ${mutedText(theme)}`}>
              Coverage by Topic
              <InfoTooltip label="About Coverage by Topic"><CoverageByTopicDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="pl-2">
            <div className="h-[260px]">
              {topicDistData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topicDistData}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridStroke} strokeOpacity={0.4} />
                    <XAxis dataKey="name" stroke={axisStroke} fontSize={9} />
                    <YAxis stroke={axisStroke} fontSize={9} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="value" fill={accent} radius={[3, 3, 0, 0]} isAnimationActive={true} animationDuration={850} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className={`flex items-center justify-center h-full font-mono text-xs ${mutedText(theme)}`}>No topics mapped.</div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Reputation Trend Card */}
        <Card className={cardStyle}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center ${mutedText(theme)}`}>
              Reputation Score Over Time
              <InfoTooltip label="About Reputation Score"><ReputationScoreDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[260px]">
            {repHistory.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RechartsLineChart data={repHistory} margin={{ top: 15, right: 30, bottom: 10, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridStroke} strokeOpacity={0.4} />
                  <XAxis dataKey="date" stroke={axisStroke} fontSize={9} tickLine={false} axisLine={false} />
                  <YAxis stroke={axisStroke} fontSize={9} tickLine={false} axisLine={false} domain={['dataMin - 2', 'dataMax + 2']} tickFormatter={(v) => Number(v).toFixed(0)} />
                  <Tooltip contentStyle={tooltipStyle} formatter={tooltipScoreFormatter} />
                  <Line
                    type="monotone"
                    dataKey="score"
                    stroke={accent}
                    strokeWidth={2}
                    dot={{ r: 3.5, stroke: accent, fill: isDark ? '#09090b' : '#ffffff', strokeWidth: 1.5 }}
                    activeDot={{ r: 6 }}
                    isAnimationActive={true}
                    animationDuration={850}
                  />
                </RechartsLineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full space-y-2">
                <LineChart className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
                <p className={`font-mono text-xs ${mutedText(theme)}`}>No historical reputation data available.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Sentiment Trend Card */}
        <Card className={cardStyle}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center ${mutedText(theme)}`}>
              Average Sentiment Over Time
              <InfoTooltip label="About Average Sentiment Over Time"><AverageSentimentTrendDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[260px]">
            {sentimentTrendData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RechartsLineChart data={sentimentTrendData} margin={{ top: 15, right: 30, bottom: 10, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridStroke} strokeOpacity={0.4} />
                  <XAxis dataKey="date" stroke={axisStroke} fontSize={9} tickLine={false} axisLine={false} />
                  <YAxis stroke={axisStroke} fontSize={9} tickLine={false} axisLine={false} domain={[-1, 1]} />
                  <Tooltip content={<SentimentTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="Sentiment"
                    stroke={accent}
                    strokeWidth={2}
                    dot={<SentimentDot />}
                    activeDot={{ r: 6 }}
                    isAnimationActive={true}
                    animationDuration={850}
                  />
                </RechartsLineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full space-y-2">
                <LineChart className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
                <p className={`font-mono text-xs ${mutedText(theme)}`}>No sentiment timeline data.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
