import React, { useMemo } from "react";
import { Compass, Users, MessageSquare, AlertOctagon, TrendingUp, Cpu } from "lucide-react";
import { getRiskLevel, RISK_THRESHOLDS } from "@/utils/riskLevel";
import { 
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer, RadarChart, PolarGrid, 
  PolarAngleAxis, PolarRadiusAxis, Radar, LineChart as RechartsLineChart, Line,
  AreaChart, Area, BarChart, Bar, Cell
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";

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
      { label: "Top Narrative Theme", value: topNarrative, desc: "Most discussed narrative", icon: Compass, color: "text-[#D4AF37]" },
      { label: "Aggregate Mentions", value: totalMentions, desc: "Cumulative narratives volume", icon: Users, color: "text-[#38BDF8]" }
    ];
  }, [narrativeBubbleData]);

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
    const colors = ["#38BDF8", "#D4AF37", "#A855F7", "#F97316", "#10B981", "#EF4444"];
    return colors[index % colors.length];
  };

  const tooltipStyle = {
    backgroundColor: 'rgba(11, 15, 25, 0.95)',
    borderColor: '#1e293b',
    borderRadius: '8px',
    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.8)',
    color: '#e2e8f0',
    fontFamily: 'monospace',
    fontSize: '11px',
    padding: '12px'
  };

  const cardStyle = "bg-[#060B18]/60 border-[#1F2937]/70 shadow-[inset_0_1.5px_2px_rgba(255,255,255,0.06)] hover:border-[#D4AF37]/35 hover:shadow-[0_0_20px_rgba(212,175,55,0.12)] hover:-translate-y-0.5 transition-all duration-300 rounded-xl";

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
          <div key={x} className="h-[280px] bg-[#060B18]/40 border border-[#1F2937]/60 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Card className="bg-[#060B18]/60 border-red-500/20 h-96">
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
              className="bg-[#060B18]/60 border border-[#1F2937]/60 shadow-[inset_0_1px_2px_rgba(255,255,255,0.05)] rounded-xl p-4 flex flex-col justify-between hover:border-[#D4AF37]/30 transition-all duration-300"
            >
              <div className="flex justify-between items-start mb-2">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">{k.label}</span>
                <Icon className={`h-4 w-4 ${k.color}`} />
              </div>
              <div>
                <span className={`text-xl font-bold block ${k.color} truncate`}>{k.value}</span>
                <span className="text-[8px] text-slate-500">{k.desc}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Narrative Landscape Matrix (Bubble Chart with Glow filters) */}
        <Card className={cardStyle}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Narrative Landscape Matrix (Velocity × Risk)</CardTitle>
          </CardHeader>
          <CardContent className="h-[280px] pl-2">
            {normalizedBubbleData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 20, right: 25, bottom: 20, left: 10 }}>
                  <defs>
                    <filter id="glow-crit" x="-30%" y="-30%" width="160%" height="160%">
                      <feGaussianBlur stdDeviation="4" result="blur" />
                      <feComponentTransfer in="blur" result="glow">
                        <feFuncA type="linear" slope="0.6" />
                      </feComponentTransfer>
                      <feMerge>
                        <feMergeNode in="glow" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                    <filter id="glow-high" x="-30%" y="-30%" width="160%" height="160%">
                      <feGaussianBlur stdDeviation="3.5" result="blur" />
                      <feComponentTransfer in="blur" result="glow">
                        <feFuncA type="linear" slope="0.45" />
                      </feComponentTransfer>
                      <feMerge>
                        <feMergeNode in="glow" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                    <filter id="glow-med" x="-30%" y="-30%" width="160%" height="160%">
                      <feGaussianBlur stdDeviation="3" result="blur" />
                      <feComponentTransfer in="blur" result="glow">
                        <feFuncA type="linear" slope="0.35" />
                      </feComponentTransfer>
                      <feMerge>
                        <feMergeNode in="glow" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" strokeOpacity={0.2} />
                  <XAxis type="number" dataKey="strength" name="Velocity" stroke="#94A3B8" fontSize={9} domain={xAxisDomain} label={{ value: 'Narrative Velocity', position: 'bottom', fill: '#94A3B8', offset: 0, fontSize: 9 }} />
                  <YAxis type="number" dataKey="risk" name="Risk Score" stroke="#94A3B8" fontSize={9} domain={yAxisDomain} label={{ value: 'Risk Score', angle: -90, position: 'left', fill: '#94A3B8', fontSize: 9 }} />
                  <ZAxis type="number" dataKey="logVolume" range={[80, 500]} name="Volume" />
                  <Tooltip 
                    cursor={{ strokeDasharray: '3 3' }} 
                    contentStyle={tooltipStyle}
                    content={({ active, payload }) => {
                      if (active && payload && payload.length > 0) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-[#0b0f19]/95 border border-[#1e293b] rounded-lg p-3 font-mono text-[10px] space-y-1">
                            <div className="font-bold text-[#D4AF37] border-b border-[#1F2937] pb-1 mb-1 truncate max-w-[200px]">
                              {data.name}
                            </div>
                            <div className="flex justify-between space-x-6">
                              <span className="text-slate-500">Volume (Mentions):</span>
                              <span className="text-slate-200 font-bold">{data.mentions}</span>
                            </div>
                            <div className="flex justify-between space-x-6">
                              <span className="text-slate-500">Risk Score:</span>
                              <span className="text-red-400 font-bold">{data.risk}</span>
                            </div>
                            <div className="flex justify-between space-x-6">
                              <span className="text-slate-500">Velocity:</span>
                              <span className="text-slate-200 font-bold">{data.strength?.toFixed(1)}</span>
                            </div>
                            <div className="flex justify-between space-x-6">
                              <span className="text-slate-500">Classification:</span>
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
              <div className="flex items-center justify-center h-full text-slate-500 font-mono text-xs">No narratives to map.</div>
            )}
          </CardContent>
        </Card>

        {/* Competitor Radar Position Compare */}
        <Card className={cardStyle}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Competitor Positioning Radar Grid</CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center items-center h-[280px]">
            {normalizedBenchmarks.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="75%" data={competitorRadarData}>
                  <PolarGrid stroke="#1F2937" />
                  <PolarAngleAxis dataKey="subject" stroke="#94A3B8" fontSize={9} />
                  <PolarRadiusAxis stroke="#1F2937" tick={false} />
                  <Radar name={activeClientName} dataKey={activeClientName} stroke="#D4AF37" fill="#D4AF37" fillOpacity={0.25} isAnimationActive={true} />
                  {normalizedBenchmarks.map((b, idx) => (
                    <Radar key={idx} name={b.competitor_name} dataKey={b.competitor_name} stroke="#38BDF8" fill="#38BDF8" fillOpacity={0.06} isAnimationActive={true} />
                  ))}
                  <Tooltip contentStyle={tooltipStyle} />
                </RadarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full space-y-2">
                <Compass className="h-6 w-6 text-slate-500 opacity-60" />
                <p className="text-slate-500 font-mono text-xs">No competitor radar comparative data.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Executive Historical Trend */}
        <Card className={`${cardStyle} md:col-span-2`}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Executive Figures Historical Trend</CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[280px]">
            {trendChartDataWithMA.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RechartsLineChart data={trendChartDataWithMA} margin={{ top: 15, right: 30, bottom: 10, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                  <XAxis dataKey="date" stroke="#94A3B8" fontSize={9} />
                  <YAxis stroke="#94A3B8" fontSize={9} />
                  <Tooltip 
                    shared 
                    contentStyle={tooltipStyle} 
                  />
                  {Object.keys(execHistory || {}).map((name, idx) => {
                    const colors = ["#D4AF37", "#38BDF8", "#EF4444", "#EAB308", "#10B981"];
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
                <Users className="h-6 w-6 text-slate-500 opacity-60" />
                <p className="text-slate-500 font-mono text-xs">No leadership figures data to track.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Daily Ingestion Ingestion Volume (Stacked Area Chart) */}
        <Card className={cardStyle}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Daily Ingestion Ingestion Volume</CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[240px]">
            {stackedTimelineData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={stackedTimelineData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                  <XAxis dataKey="date" stroke="#94A3B8" fontSize={9} />
                  <YAxis stroke="#94A3B8" fontSize={9} />
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
              <div className="flex items-center justify-center h-full text-slate-500 font-mono text-xs">No timeline volume data.</div>
            )}
          </CardContent>
        </Card>

        {/* Source Distribution (Ranked Horizontal Bar Chart) */}
        <Card className={cardStyle}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Sources Distribution Matrix</CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[240px]">
            {sortedSourceData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sortedSourceData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#1F2937" strokeOpacity={0.2} />
                  <XAxis type="number" stroke="#94A3B8" fontSize={9} />
                  <YAxis dataKey="name" type="category" stroke="#94A3B8" fontSize={9} width={90} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Bar dataKey="value" fill="#38BDF8" radius={[0, 3, 3, 0]} isAnimationActive={true} animationDuration={850}>
                    {sortedSourceData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={getSourceColor(entry.name, index)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-500 font-mono text-xs">No source contribution data.</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
