import React, { useMemo } from "react";
import { Compass, Users, MessageSquare, AlertOctagon, TrendingUp, Cpu } from "lucide-react";
import { getRiskLevel, RISK_THRESHOLDS } from "@/utils/riskLevel";
import { formatScore, tooltipScoreFormatter } from "@/utils/formatScore";
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, LineChart as RechartsLineChart, Line,
  AreaChart, Area, BarChart, Bar, Cell
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";

export interface NarrativeAnalyticsPanelProps {
  narrativeBubbleData: any[];
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
  narrativeBubbleData = [],
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
  const accentColor = isDark ? "text-[#00F5D4]" : "text-[#3B82F6]";

  // 1. KPI Summaries based on live data
  const kpis = useMemo(() => {
    const totalNarratives = narrativeBubbleData.length;
    const highRiskCount = narrativeBubbleData.filter(n => (n.risk || 0) > RISK_THRESHOLDS.MEDIUM_TO_HIGH).length;

    const sortedByMentions = [...narrativeBubbleData].sort((a, b) => b.mentions - a.mentions);
    const topNarrative = sortedByMentions.length > 0 ? sortedByMentions[0].name : "None";

    const totalMentions = narrativeBubbleData.reduce((sum, n) => sum + (n.mentions || 0), 0);

    return [
      { label: "Total Narratives", value: totalNarratives, desc: "Identified media clusters", icon: MessageSquare, color: "text-purple-400" },
      { label: "High-Risk Clusters", value: highRiskCount, desc: "Critical/High risk narratives", icon: AlertOctagon, color: "text-red-500" },
      { label: "Top Narrative Theme", value: topNarrative, desc: "Most discussed narrative", icon: Compass, color: accentColor },
      { label: "Aggregate Mentions", value: totalMentions, desc: "Cumulative narratives volume", icon: Users, color: accentColor }
    ];
  }, [narrativeBubbleData, accentColor]);

  // 2. Normalization & Logarithmic bubble scaling for the Scatter / Bubble chart
  const { normalizedBubbleData, minStrength, maxStrength, minRisk, maxRisk } = useMemo(() => {
    let minStrength = 0;
    let maxStrength = 10;
    let minRisk = 0;
    let maxRisk = 100;

    if (narrativeBubbleData.length > 0) {
      const strengths = narrativeBubbleData.map(n => n.strength || 0);
      const risks = narrativeBubbleData.map(n => n.risk || 0);
      minStrength = Math.min(...strengths);
      maxStrength = Math.max(...strengths);
      minRisk = Math.min(...risks);
      maxRisk = Math.max(...risks);
    }

    // Client-side Logarithmic transformation to prevent extreme size variations
    const data = narrativeBubbleData.map(entry => {
      const mentions = entry.mentions || 0;
      // Math.log2 gives a smoother radius mapping for ZAxis
      const logVolume = Math.round(Math.log2(mentions + 2) * 25 + 10);
      return {
        ...entry,
        logVolume
      };
    });

    return { 
      normalizedBubbleData: data, 
      minStrength, 
      maxStrength, 
      minRisk, 
      maxRisk 
    };
  }, [narrativeBubbleData]);

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

  // Dynamic axis limits with padding to prevent edge clipping
  const xAxisDomain = useMemo(() => {
    const min = Math.max(0, minStrength - 1);
    const max = maxStrength + 1;
    return [min, max];
  }, [minStrength, maxStrength]);

  const yAxisDomain = useMemo(() => {
    const min = Math.max(0, minRisk - 5);
    const max = Math.min(100, maxRisk + 5);
    return [min, max];
  }, [minRisk, maxRisk]);

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
      {/* Top KPI Summary row */}
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
                <span className={`text-[10px] uppercase tracking-wider ${mutedText(theme)}`}>{k.label}</span>
                <Icon className={`h-4 w-4 ${k.color}`} />
              </div>
              <div>
                <span className={`text-xl font-bold block ${k.color} truncate`}>{k.value}</span>
                <span className={`text-[8px] ${mutedText(theme)}`}>{k.desc}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Narrative Landscape Matrix (Bubble Chart with Glow filters).
            Full-width (md:col-span-2): used to share this row with the
            Competitor Positioning Radar Grid card (removed -- its data was
            noise), so it now spans the row alone rather than leaving an
            empty half-width gap next to it. */}
        <Card className={`${cardStyle} md:col-span-2`}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Narrative Landscape Matrix (Velocity × Risk)</CardTitle>
          </CardHeader>
          <CardContent className="h-[280px] pl-2">
            {normalizedBubbleData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 20, right: 25, bottom: 20, left: 10 }}>
                  {/* Glow intensity is theme-gated: a blur/alpha tuned to
                      pop against dark mode's near-black body reads as a
                      blurry, muddy smudge against light mode's white card --
                      light mode gets a lower blur radius and lower alpha so
                      markers stay crisp instead. */}
                  <defs>
                    <filter id="glow-crit" x="-30%" y="-30%" width="160%" height="160%">
                      <feGaussianBlur stdDeviation={isDark ? "4" : "1.5"} result="blur" />
                      <feComponentTransfer in="blur" result="glow">
                        <feFuncA type="linear" slope={isDark ? "0.6" : "0.35"} />
                      </feComponentTransfer>
                      <feMerge>
                        <feMergeNode in="glow" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                    <filter id="glow-high" x="-30%" y="-30%" width="160%" height="160%">
                      <feGaussianBlur stdDeviation={isDark ? "3.5" : "1.25"} result="blur" />
                      <feComponentTransfer in="blur" result="glow">
                        <feFuncA type="linear" slope={isDark ? "0.45" : "0.28"} />
                      </feComponentTransfer>
                      <feMerge>
                        <feMergeNode in="glow" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                    <filter id="glow-med" x="-30%" y="-30%" width="160%" height="160%">
                      <feGaussianBlur stdDeviation={isDark ? "3" : "1"} result="blur" />
                      <feComponentTransfer in="blur" result="glow">
                        <feFuncA type="linear" slope={isDark ? "0.35" : "0.2"} />
                      </feComponentTransfer>
                      <feMerge>
                        <feMergeNode in="glow" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} strokeOpacity={0.4} />
                  <XAxis type="number" dataKey="strength" name="Velocity" stroke={axisStroke} fontSize={9} domain={xAxisDomain} label={{ value: 'Narrative Velocity', position: 'bottom', fill: axisStroke, offset: 0, fontSize: 9 }} />
                  <YAxis type="number" dataKey="risk" name="Risk Score" stroke={axisStroke} fontSize={9} domain={yAxisDomain} label={{ value: 'Risk Score', angle: -90, position: 'left', fill: axisStroke, fontSize: 9 }} />
                  <ZAxis type="number" dataKey="logVolume" range={[80, 500]} name="Volume" />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    contentStyle={tooltipStyle}
                    content={({ active, payload }) => {
                      if (active && payload && payload.length > 0) {
                        const data = payload[0].payload;
                        return (
                          <div className={`rounded-lg p-3 font-mono text-[10px] space-y-1 border ${isDark ? "bg-zinc-950/95 border-white/[0.12]" : "bg-white/95 border-black/[0.08]"}`}>
                            <div className="font-bold border-b pb-1 mb-1 truncate max-w-[200px]" style={{ color: accent, borderColor: isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.06)" }}>
                              {data.name}
                            </div>
                            <div className="flex justify-between space-x-6">
                              <span className={mutedText(theme)}>Volume (Mentions):</span>
                              <span className={`font-bold ${bodyText(theme)}`}>{data.mentions}</span>
                            </div>
                            <div className="flex justify-between space-x-6">
                              <span className={mutedText(theme)}>Risk Score:</span>
                              <span className="text-red-500 font-bold">{formatScore(data.risk, 1)}</span>
                            </div>
                            <div className="flex justify-between space-x-6">
                              <span className={mutedText(theme)}>Velocity:</span>
                              <span className={`font-bold ${bodyText(theme)}`}>{formatScore(data.strength, 1)}</span>
                            </div>
                            <div className="flex justify-between space-x-6">
                              <span className={mutedText(theme)}>Classification:</span>
                              <span className="text-purple-400 font-bold">{data.type}</span>
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Scatter name="Narratives" data={normalizedBubbleData} isAnimationActive={true}>
                    {normalizedBubbleData.map((entry: any, index: number) => {
                      const risk = entry.risk || 0;
                      const level = getRiskLevel(risk);
                      let fill = "#10B981";
                      let filter = undefined;
                      if (level === "CRITICAL") {
                        fill = "#EF4444";
                        filter = "url(#glow-crit)";
                      } else if (level === "HIGH") {
                        fill = "#F97316";
                        filter = "url(#glow-high)";
                      } else if (level === "MEDIUM") {
                        fill = "#EAB308";
                        filter = "url(#glow-med)";
                      }
                      return (
                        <Cell 
                          key={`bubble-${index}`} 
                          fill={fill} 
                          stroke="#fff" 
                          strokeWidth={1.5}
                          filter={filter}
                        />
                      );
                    })}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full font-mono text-xs ${mutedText(theme)}`}>No narratives to map.</div>
            )}
          </CardContent>
        </Card>

        {/* Executive Historical Trend */}
        <Card className={`${cardStyle} md:col-span-2`}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Executive Figures Historical Trend</CardTitle>
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

        {/* Daily Ingestion Ingestion Volume (Stacked Area Chart) */}
        <Card className={cardStyle}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Daily Ingestion Ingestion Volume</CardTitle>
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
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Sources Distribution Matrix</CardTitle>
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
