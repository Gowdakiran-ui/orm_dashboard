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
import { ReputationScoreDefinition, SentimentScaleDefinition } from "@/lib/metricDefinitions";

export interface OverviewAnalyticsPanelProps {
  sentimentDistData: any[];
  topicDistData: any[];
  repHistory: any[];
  sentimentTrendData: any[];
  loading?: boolean;
  error?: string | null;
  /** Tier 3 Part A: deep-link a sentiment-trend point's driving narrative into
   *  the narrative drawer -- same navigateTo/openNarrativeDrawer mechanism
   *  RiskTab and ReputationSummaryCard already use, not a new nav pattern. */
  onViewNarrative?: (narrativeName: string) => void;
}

export function OverviewAnalyticsPanel({
  sentimentDistData = [],
  topicDistData = [],
  repHistory = [],
  sentimentTrendData = [],
  loading = false,
  error = null,
  onViewNarrative
}: OverviewAnalyticsPanelProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const accentColor = isDark ? "text-[#00F5D4]" : "text-[#3B82F6]";
  // 1. KPI Summaries based on live prop telemetry
  const kpis = useMemo(() => {
    const latestRep = repHistory.length > 0 ? repHistory[0].score : 0;
    const latestRepScore = latestRep > 0 ? latestRep.toFixed(2) : "0.00";
    
    const latestSent = sentimentTrendData.length > 0 ? sentimentTrendData[0].Sentiment : 0.0;
    const latestSentScore = latestSent > 0 ? `+${latestSent.toFixed(2)}` : latestSent.toFixed(2);
    
    const dimensionsCount = topicDistData.length;
    
    const posVal = sentimentDistData.find(d => d.name === "Positive")?.value || 0;
    const totalVal = sentimentDistData.reduce((acc, curr) => acc + (curr.value || 0), 0);
    const posRatio = totalVal > 0 ? `${((posVal / totalVal) * 100).toFixed(0)}%` : "0%";

    return [
      { label: "Avg Reputation", value: latestRepScore, desc: "Overall reputation score", icon: Activity, color: accentColor, def: <ReputationScoreDefinition /> },
      { label: "Sentiment Score", value: latestSentScore, desc: "How positive coverage is (-1.0 to +1.0)", icon: Smile, color: accentColor, def: <SentimentScaleDefinition /> },
      { label: "Topics Covered", value: dimensionsCount, desc: "Distinct topics found in coverage", icon: BarChart3, color: "text-purple-400", def: undefined as React.ReactNode },
      { label: "Positive Share", value: posRatio, desc: "Favorable media percentage", icon: TrendingUp, color: "text-emerald-400", def: undefined as React.ReactNode }
    ];
  }, [repHistory, sentimentTrendData, topicDistData, sentimentDistData, accentColor]);

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

  // Tier 3 Part A: real hover explanation for the sentiment trend, built
  // from the driver useAnalytics.sentimentTrendData already computed
  // (narrative name + narrative_engine.py's own root_cause) -- this
  // replaces recharts' default single-value tooltip on this one chart
  // instead of introducing a second popover pattern next to it.
  const SentimentTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || !payload.length) return null;
    const point = payload[0].payload;
    const driver = point.driver as { name: string; rootCause: string | null; mentions: number } | null;
    return (
      <div style={tooltipStyle} className="space-y-1 max-w-[260px]">
        <div className="font-bold">{label}</div>
        <div>Sentiment: {point.Sentiment >= 0 ? "+" : ""}{point.Sentiment.toFixed(2)}</div>
        {point.meaningful && driver && driver.rootCause ? (
          <div className="pt-1 border-t border-current/10 space-y-0.5">
            <div className="text-[10px] uppercase opacity-70">Driving narrative ({driver.mentions} doc{driver.mentions === 1 ? "" : "s"})</div>
            <div className="font-bold">{driver.name}</div>
            <div className="text-[10px] opacity-80 leading-snug">{driver.rootCause}</div>
            {onViewNarrative && <div className="text-[9px] opacity-60 italic">Click point to open narrative &rarr;</div>}
          </div>
        ) : point.meaningful ? (
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
    const { cx, cy, payload } = props;
    if (cx === undefined || cy === undefined) return null;
    const hasDriver = Boolean(payload?.meaningful && payload?.driver?.rootCause && onViewNarrative);
    return (
      <circle
        cx={cx}
        cy={cy}
        r={3.5}
        stroke={accent}
        strokeWidth={1.5}
        fill={isDark ? "#09090b" : "#ffffff"}
        style={{ cursor: hasDriver ? "pointer" : "default" }}
        onClick={() => {
          if (hasDriver) onViewNarrative!(payload.driver.name);
        }}
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
      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 font-mono">
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
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Sentiment Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center items-center h-[260px]">
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
                    isAnimationActive={true}
                    animationDuration={850}
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
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Coverage by Topic</CardTitle>
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
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Reputation Score Over Time</CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[260px]">
            {repHistory.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RechartsLineChart data={repHistory} margin={{ top: 15, right: 30, bottom: 10, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridStroke} strokeOpacity={0.4} />
                  <XAxis dataKey="date" stroke={axisStroke} fontSize={9} tickLine={false} axisLine={false} />
                  <YAxis stroke={axisStroke} fontSize={9} tickLine={false} axisLine={false} domain={['dataMin - 2', 'dataMax + 2']} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(value: unknown) => (typeof value === "number" ? value.toFixed(2) : (value as React.ReactNode))} />
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
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Average Sentiment Over Time</CardTitle>
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
