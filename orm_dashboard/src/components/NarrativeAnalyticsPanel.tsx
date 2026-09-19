import React, { useMemo } from "react";
import { Users, TrendingUp, Cpu } from "lucide-react";
import { formatScore, tooltipScoreFormatter } from "@/utils/formatScore";
import {
  XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, LineChart as RechartsLineChart, Line,
  AreaChart, Area, BarChart, Bar, Cell
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import {
  ReputationScoreDefinition,
  DailyIngestionVolumeDefinition,
  SourcesDistributionDefinition,
} from "@/lib/metricDefinitions";

export interface NarrativeAnalyticsPanelProps {
  competitorRadarData: any[];
  execTrendChartData: any[];
  pipelineTimelineData: any[];
  sourceContData: any[];
  activeClientName: string;
  normalizedBenchmarks: any[];
  execHistory: any;
  documents?: any[];
  loading?: boolean;
  error?: string | null;
}

export function NarrativeAnalyticsPanel({
  competitorRadarData = [],
  execTrendChartData = [],
  pipelineTimelineData = [],
  sourceContData = [],
  activeClientName,
  normalizedBenchmarks = [],
  execHistory,
  documents = [],
  loading = false,
  error = null
}: NarrativeAnalyticsPanelProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";

  // 3. Stacked Ingestion Volume Reshaping
  const { stackedTimelineData, uniqueSources } = useMemo(() => {
    const dateBuckets: Record<string, Record<string, number>> = {};
    const sourcesSet = new Set<string>();
    
    (documents || []).forEach(d => {
      if (d && d.timestamp) {
        const dateStr = new Date(d.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        const source = d.source || "RSS Feed";
        sourcesSet.add(source);
        if (!dateBuckets[dateStr]) {
          dateBuckets[dateStr] = {};
        }
        dateBuckets[dateStr][source] = (dateBuckets[dateStr][source] || 0) + 1;
      }
    });

    const uniqueSources = Array.from(sourcesSet);
    const stackedTimelineData = Object.entries(dateBuckets)
      .map(([date, sourceCounts]) => {
        const row: Record<string, any> = { date };
        uniqueSources.forEach(s => {
          row[s] = sourceCounts[s] || 0;
        });
        return row;
      })
      .reverse();

    return { stackedTimelineData, uniqueSources };
  }, [documents]);

  // 4. Ranked Horizontal Sources Distribution Reshaping
  const sortedSourceData = useMemo(() => {
    const counts: Record<string, number> = {};
    (documents || []).forEach(d => {
      if (d) {
        const s = d.source || "RSS Feed";
        counts[s] = (counts[s] || 0) + 1;
      }
    });
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [documents]);

  // 5. Moving Average Calculation for Executive Historical Trends
  const trendChartDataWithMA = useMemo(() => {
    if (!execTrendChartData || execTrendChartData.length === 0) return [];
    
    const data = execTrendChartData.map(d => ({ ...d }));
    
    Object.keys(execHistory || {}).forEach(name => {
      const values = data.map(d => d[name]);
      const validPoints = values.filter(v => typeof v === 'number').length;
      
      if (validPoints >= 5) {
        const windowSize = 5;
        for (let i = 0; i < data.length; i++) {
          const slice = data.slice(Math.max(0, i - windowSize + 1), i + 1);
          const vals = slice.map(d => d[name]).filter(v => typeof v === 'number');
          if (vals.length > 0) {
            const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
            data[i][`${name}_MA`] = Number(avg.toFixed(1));
          }
        }
      }
    });
    return data;
  }, [execTrendChartData, execHistory]);

  const getSourceColor = (source: string, index: number) => {
    const colors = [accent, isDark ? "#7B2CBF" : "#8B5CF6", "#A855F7", "#F97316", "#10B981", "#EF4444"];
    return colors[index % colors.length];
  };

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

  if (loading) {
    return (
      <div className="grid gap-6 md:grid-cols-2 animate-pulse">
        {[1, 2, 3, 4].map(x => (
          <div key={x} className={`h-[280px] rounded-3xl ${glassTokens[theme].card}`} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Card className={`${glassCard(theme)} border-red-500/20 h-96`}>
        <TelemetryErrorWidget title="Narrative Analytics Telemetry Offline" message={error} />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        {/* Executive Historical Trend */}
        <Card className={`${cardStyle} md:col-span-2`}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center ${mutedText(theme)}`}>
              Notable People in Coverage — Historical Trend
              <InfoTooltip label="About Reputation Score"><ReputationScoreDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[280px]">
            {trendChartDataWithMA.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RechartsLineChart data={trendChartDataWithMA} margin={{ top: 15, right: 30, bottom: 10, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridStroke} strokeOpacity={0.4} />
                  <XAxis dataKey="date" stroke={axisStroke} fontSize={9} />
                  <YAxis stroke={axisStroke} fontSize={9} />
                  <Tooltip
                    shared
                    formatter={tooltipScoreFormatter}
                    contentStyle={tooltipStyle}
                  />
                  {Object.keys(execHistory || {}).map((name, idx) => {
                    const colors = [accent, isDark ? "#7B2CBF" : "#8B5CF6", "#EF4444", "#EAB308", "#10B981"];
                    const color = colors[idx % colors.length];
                    const hasMA = trendChartDataWithMA.some(d => d[`${name}_MA`] !== undefined);

                    return (
                      <React.Fragment key={idx}>
                        {/* Primary Trend Line */}
                        <Line 
                          type="monotone" 
                          dataKey={name} 
                          stroke={color} 
                          strokeWidth={2} 
                          dot={{ r: 3, strokeWidth: 1 }} 
                          activeDot={{ r: 5 }} 
                          isAnimationActive={true}
                          animationDuration={850}
                        />
                        {/* 5-Period Moving Average Line */}
                        {hasMA && (
                          <Line 
                            type="monotone" 
                            dataKey={`${name}_MA`} 
                            stroke={color} 
                            strokeWidth={1.2} 
                            strokeDasharray="4 4" 
                            dot={false}
                            name={`${name} (5-day MA)`} 
                            isAnimationActive={true}
                            animationDuration={850}
                          />
                        )}
                      </React.Fragment>
                    );
                  })}
                </RechartsLineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full space-y-2">
                <Users className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
                <p className={`font-mono text-xs ${mutedText(theme)}`}>No leadership figures data to track.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Daily Ingestion Volume (Stacked Area Chart) */}
        <Card className={cardStyle}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center ${mutedText(theme)}`}>
              Daily Ingestion Volume
              <InfoTooltip label="About Daily Ingestion Volume"><DailyIngestionVolumeDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[240px]">
            {stackedTimelineData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={stackedTimelineData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridStroke} strokeOpacity={0.4} />
                  <XAxis dataKey="date" stroke={axisStroke} fontSize={9} />
                  <YAxis stroke={axisStroke} fontSize={9} />
                  <Tooltip contentStyle={tooltipStyle} />
                  {uniqueSources.map((source, index) => (
                    <Area
                      key={source}
                      type="monotone"
                      dataKey={source}
                      stackId="1"
                      stroke={getSourceColor(source, index)}
                      fill={getSourceColor(source, index)}
                      fillOpacity={0.25}
                      strokeWidth={1.5}
                      isAnimationActive={true}
                      animationDuration={850}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full font-mono text-xs ${mutedText(theme)}`}>No timeline volume data.</div>
            )}
          </CardContent>
        </Card>

        {/* Source Distribution (Ranked Horizontal Bar Chart) */}
        <Card className={cardStyle}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center ${mutedText(theme)}`}>
              Sources Distribution Matrix
              <InfoTooltip label="About Sources Distribution"><SourcesDistributionDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[240px]">
            {sortedSourceData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sortedSourceData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={gridStroke} strokeOpacity={0.4} />
                  <XAxis type="number" stroke={axisStroke} fontSize={9} />
                  <YAxis dataKey="name" type="category" stroke={axisStroke} fontSize={9} width={90} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="value" fill={accent} radius={[0, 3, 3, 0]} isAnimationActive={true} animationDuration={850}>
                    {sortedSourceData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={getSourceColor(entry.name, index)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full font-mono text-xs ${mutedText(theme)}`}>No source contribution data.</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
