import React, { useState, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { 
  Sparkles, Compass, Users, MessageSquare, AlertOctagon, TrendingUp, 
  Search, ShieldAlert, Cpu, CheckCircle2, X, ExternalLink
} from "lucide-react";
import { 
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, 
  Tooltip, Cell, LineChart, Line, CartesianGrid, AreaChart, Area, LabelList 
} from "recharts";
import { NarrativeIntelligenceWorkbench } from "@/components/NarrativeIntelligenceWorkbench";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, glassPill, glassPrimaryButton, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";

export interface NarrativesTabProps {
  documentsLoading: boolean;
  executivesLoading: boolean;
  narrativesLoading: boolean;
  documents: any[];
  executives: any[];
  narratives: any[];
  activeClientName: string;
  selectedNarrative: string | null;
  setSelectedNarrative: (narrative: string | null) => void;
  narrativesError: string | null;
  clientId: string | null;
}

export function NarrativesTab({
  documentsLoading,
  executivesLoading,
  narrativesLoading,
  documents = [],
  executives = [],
  narratives = [],
  activeClientName,
  selectedNarrative,
  setSelectedNarrative,
  narrativesError,
  clientId
}: NarrativesTabProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const accentColor = isDark ? "text-[#00F5D4]" : "text-[#3B82F6]";

  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedTopic, setSelectedTopic] = useState("all");
  const [selectedExec, setSelectedExec] = useState("all");
  const [minMentions, setMinMentions] = useState(0);
  const [minRisk, setMinRisk] = useState(0);

  // Tactical Drawer state supporting client, executive, narrative, and document nodes
  const [drawerData, setDrawerData] = useState<{
    type: "client" | "executive" | "narrative" | "document";
    data: any;
  } | null>(null);

  // Hover state for Scatter chart bubbles
  const [hoveredScatterIndex, setHoveredScatterIndex] = useState<number | null>(null);

  // Dynamic Topics list
  const topicsList = useMemo(() => {
    const topics = new Set<string>();
    documents.forEach(d => d.topic && topics.add(d.topic));
    return Array.from(topics);
  }, [documents]);

  // Compute KPI summaries from live backend data
  const summaryKpis = useMemo(() => {
    const totalNarratives = narratives.length;
    const totalExecs = executives.length;
    const totalDocs = documents.length;

    const highestRiskNarr = [...narratives].sort((a, b) => (b.risk || 0) - (a.risk || 0))[0]?.name || "None Detected";
    const fastestGrowingNarr = [...narratives].sort((a, b) => (b.trend || 0) - (a.trend || 0))[0]?.name || "None Detected";
    
    const mostMentionedExec = [...executives].sort((a, b) => (b.mention_count || 0) - (a.mention_count || 0))[0]?.name || "None Detected";
    
    // Average risk score across documents
    const avgRiskScore = totalDocs > 0 
      ? (documents.reduce((sum, d) => sum + (d.risk || 0), 0) / totalDocs).toFixed(1)
      : "0.0";

    const avgNarrativeStrength = totalNarratives > 0
      ? (narratives.reduce((sum, n) => sum + (n.trend || 0), 0) / totalNarratives).toFixed(1)
      : "0.0";

    return [
      { label: "Monitored Narratives", value: totalNarratives, desc: "Active media clusters", color: accentColor },
      { label: "Tracked Leaders", value: totalExecs, desc: "Monitored corporate heads", color: accentColor },
      { label: "Scanned Documents", value: totalDocs, desc: "Pipeline document pool", color: "text-purple-400" },
      { label: "Highest Risk Narrative", value: highestRiskNarr, desc: "Requires strategic review", color: "text-red-500" },
      { label: "Fastest Growing Narrative", value: fastestGrowingNarr, desc: "High velocity trend", color: "text-orange-400" },
      { label: "Most Mentioned Executive", value: mostMentionedExec, desc: "Overall visibility", color: "text-indigo-400" },
      { label: "Average Risk Level", value: `${avgRiskScore} pts`, desc: "Risk index across feed", color: "text-rose-500" },
      { label: "Average Strength", value: `${avgNarrativeStrength}%`, desc: "Narrative velocity rate", color: "text-emerald-400" }
    ];
  }, [documents, executives, narratives, accentColor]);

  // Filtering narratives and documents based on selectors
  const filteredNarratives = useMemo(() => {
    return narratives.filter(n => {
      const matchesSearch = n.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
                            (n.type && n.type.toLowerCase().includes(searchTerm.toLowerCase()));
      const matchesMinMentions = (n.mentions || 0) >= minMentions;
      const matchesMinRisk = (n.risk || 0) >= minRisk;
      return matchesSearch && matchesMinMentions && matchesMinRisk;
    });
  }, [narratives, searchTerm, minMentions, minRisk]);

  const healthMatrixData = useMemo(() => {
    const rawData = filteredNarratives.map(n => ({
      ...n,
      label: n.name
    }));

    // Overlap resolution: nudge overlapping data points slightly
    const resolvedData = rawData.map(item => ({ ...item }));
    for (let i = 0; i < resolvedData.length; i++) {
      for (let j = i + 1; j < resolvedData.length; j++) {
        const dx = Math.abs(resolvedData[i].trend - resolvedData[j].trend);
        const dy = Math.abs(resolvedData[i].risk - resolvedData[j].risk);
        
        // If they are within 3 units in Velocity (trend) and Risk, nudge them slightly
        if (dx < 3.0 && dy < 3.0) {
          const angle = (j * 0.95) % (2 * Math.PI);
          resolvedData[j].trend += Math.cos(angle) * 2.2;
          resolvedData[j].risk += Math.sin(angle) * 2.2;
        }
      }
    }
    return resolvedData;
  }, [filteredNarratives]);

  // Creation timeline data: Group narratives by status over dates
  const timelineData = useMemo(() => {
    const buckets: Record<string, { count: number; riskSum: number }> = {};
    documents.forEach(d => {
      if (d.timestamp) {
        const dateStr = new Date(d.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        if (!buckets[dateStr]) {
          buckets[dateStr] = { count: 0, riskSum: 0 };
        }
        buckets[dateStr].count += 1;
        buckets[dateStr].riskSum += d.risk || 0;
      }
    });
    return Object.entries(buckets)
      .map(([date, val]) => ({
        date,
        Volume: val.count,
        "Average Risk": Number((val.riskSum / Math.max(1, val.count)).toFixed(0))
      }))
      .reverse();
  }, [documents]);

  const cardStyle = glassCard(theme);

  const handleTraceClick = (narrativeName: string) => {
    setSelectedNarrative(narrativeName);
    const foundNarr = narratives.find(n => n.name.toLowerCase() === narrativeName.toLowerCase());
    if (foundNarr) {
      const associatedDocs = documents.filter(d => 
        (d.narrative && d.narrative.toLowerCase() === foundNarr.name.toLowerCase()) ||
        (d.topic && foundNarr.name.toLowerCase().includes(d.topic.toLowerCase()))
      );
      
      const meta = foundNarr.evidence_metadata || {};
      const ents = meta.supporting_entities || [];
      const primaryExec = executives.find(e => ents.includes(e.entity_id))?.name || "Corporate Voice";

      setDrawerData({
        type: "narrative",
        data: {
          ...foundNarr,
          linkedExecutives: [primaryExec],
          linkedDocuments: associatedDocs.map(d => ({
            id: d.id,
            title: d.title,
            risk: d.risk,
            sentiment: d.sentiment,
            source: d.source,
            timestamp: d.timestamp,
            content: d.content,
            extracted_entities: d.extracted_entities,
            processing_status: d.processing_status,
            entity_processing_status: d.entity_processing_status,
            topic_processing_status: d.topic_processing_status,
            sentiment_processing_status: d.sentiment_processing_status,
            url: d.url
          }))
        }
      });
    }
  };

  // Custom hover-only tooltip for Narrative Health Bubble Matrix
  const BubbleTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      const sentimentColor = data.sentiment >= 0.25 ? "text-emerald-500" : data.sentiment <= -0.25 ? "text-red-500" : "text-amber-500";
      return (
        <div className={`rounded-lg p-3 font-mono text-xs space-y-1.5 shadow-2xl border ${bodyText(theme)} ${isDark ? "bg-zinc-950/95 border-white/[0.12]" : "bg-white/95 border-black/[0.08]"}`}>
          <div className="font-bold border-b pb-1 truncate max-w-[200px] uppercase" style={{ color: accent, borderColor: isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.06)" }}>
            {data.name}
          </div>
          <div className="flex justify-between space-x-6">
            <span className={mutedText(theme)}>Risk Score:</span>
            <span className="text-red-500 font-bold">{data.risk} pts</span>
          </div>
          <div className="flex justify-between space-x-6">
            <span className={mutedText(theme)}>Velocity:</span>
            <span className={`font-bold ${bodyText(theme)}`}>{data.trend?.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between space-x-6">
            <span className={mutedText(theme)}>Sentiment:</span>
            <span className={`font-bold ${sentimentColor}`}>{data.sentiment?.toFixed(2)}</span>
          </div>
          <div className="flex justify-between space-x-6">
            <span className={mutedText(theme)}>Volume:</span>
            <span className={`font-bold ${bodyText(theme)}`}>{data.mentions || 0} mentions</span>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-6 relative min-h-screen pb-16">
      
      {/* 1. Top Executive summary KPIs */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 font-mono">
        {summaryKpis.map((k, idx) => (
          <div
            key={idx}
            className={`${glassCard(theme)} p-4 flex flex-col justify-between`}
          >
            <div className={SPECULAR_LINE} />
            <span className={`text-xs uppercase tracking-wider block mb-2 ${mutedText(theme)}`}>{k.label}</span>
            <div>
              <span className={`text-lg font-bold block ${k.color} truncate`}>{k.value}</span>
              <span className={`text-xs block truncate mt-1 ${mutedText(theme)}`}>{k.desc}</span>
            </div>
          </div>
        ))}
      </div>

      {/* 2. Narrative Intelligence Workbench centerpiece */}
      <div className="mb-6">
        <NarrativeIntelligenceWorkbench 
          documents={documents}
          executives={executives}
          narratives={narratives}
          clientName={activeClientName}
          clientId={clientId || ""}
          onSelectDocument={(doc) => setDrawerData({ type: "document", data: doc })}
        />
      </div>

      {/* 4. Timeline and Health Bubble Matrix row */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Bubble Matrix Chart */}
        <Card className={cardStyle}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Narrative Overview</CardTitle>
            {/* Static legend -- this chart previously relied entirely on
                hover-only tooltips to explain color/size, which a first-time
                viewer has no way to see without already knowing to hover. */}
            <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono pt-1 ${mutedText(theme)}`}>
              <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: "#10B981" }} />Positive sentiment</span>
              <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: "#EAB308" }} />Neutral sentiment</span>
              <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: "#EF4444" }} />Negative sentiment</span>
              <span>Bubble size = coverage volume</span>
            </div>
          </CardHeader>
          <CardContent className="h-[480px]">
            {healthMatrixData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 30, right: 60, left: 30, bottom: 50 }}>
                  <XAxis
                    type="number"
                    dataKey="trend"
                    name="Velocity"
                    stroke={isDark ? "#a1a1aa" : "#71717a"}
                    fontSize={14}
                    tickLine={true}
                    label={{ value: 'Coverage Trend', position: 'bottom', fill: isDark ? "#a1a1aa" : "#71717a", offset: 25, fontSize: 15, fontFamily: 'monospace', fontWeight: 'bold' }}
                  />
                  <YAxis
                    type="number"
                    dataKey="risk"
                    name="Risk"
                    stroke={isDark ? "#a1a1aa" : "#71717a"}
                    fontSize={14}
                    tickLine={true}
                    label={{ value: 'Risk Score', angle: -90, position: 'left', fill: isDark ? "#a1a1aa" : "#71717a", offset: 25, fontSize: 15, fontFamily: 'monospace', fontWeight: 'bold' }}
                  />
                  <ZAxis type="number" dataKey="mentions" range={[150, 950]} />
                  <Tooltip 
                    cursor={{ strokeDasharray: '3 3' }} 
                    content={<BubbleTooltip />}
                  />
                  <Scatter 
                    name="Health" 
                    data={healthMatrixData}
                    onMouseEnter={(data, index) => setHoveredScatterIndex(index)}
                    onMouseLeave={() => setHoveredScatterIndex(null)}
                  >
                    {healthMatrixData.map((entry, index) => {
                      const fill = entry.sentiment >= 0.25 ? "#10B981" : entry.sentiment <= -0.25 ? "#EF4444" : "#EAB308";
                      return <Cell key={`cell-${index}`} fill={fill} stroke="#ffffff" strokeWidth={1.5} className="cursor-pointer" />;
                    })}
                    <LabelList 
                      dataKey="name" 
                      content={(props: any) => {
                        const { x, y, index, payload } = props;
                        if (payload && (hoveredScatterIndex === index || (selectedNarrative && selectedNarrative.toLowerCase() === payload.name?.toLowerCase()))) {
                          return (
                            <text
                              x={x}
                              y={y - 12}
                              fill="#ffffff"
                              fontSize={10}
                              fontFamily="monospace"
                              textAnchor="middle"
                              className="pointer-events-none drop-shadow-[0_1.5px_2px_rgba(0,0,0,0.9)]"
                            >
                              {payload.name}
                            </text>
                          );
                        }
                        return null;
                      }} 
                    />
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full font-mono text-xs ${mutedText(theme)}`}>No matching narratives found.</div>
            )}
          </CardContent>
        </Card>

        {/* Narrative Creation Timeline */}
        <Card className={cardStyle}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Coverage Volume Over Time</CardTitle>
          </CardHeader>
          <CardContent className="h-[480px] pl-2">
            {timelineData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={timelineData}>
                  <defs>
                    <linearGradient id="colorIngestVolume" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#A855F7" stopOpacity={0.35}/>
                      <stop offset="95%" stopColor="#A855F7" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={9} />
                  <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={9} />
                  <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b', fontSize: 10, fontFamily: 'monospace' }} />
                  <Area type="monotone" dataKey="Volume" stroke="#A855F7" strokeWidth={1.8} fillOpacity={1} fill="url(#colorIngestVolume)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full font-mono text-xs ${mutedText(theme)}`}>No historical volume markers.</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 5. Detailed Table register */}
      <Card className={glassCard(theme)}>
        <div className={SPECULAR_LINE} />
        <CardHeader className="pb-2">
          <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Narratives</CardTitle>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <Table className="font-mono text-xs">
            <TableHeader className={isDark ? "bg-black/20 border-white/[0.08]" : "bg-black/[0.02] border-black/[0.06]"}>
              <TableRow className={`hover:bg-transparent ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                <TableHead className={`w-1/4 ${mutedText(theme)}`}>NARRATIVE THEME</TableHead>
                <TableHead className={`text-center ${mutedText(theme)}`}>TYPE</TableHead>
                <TableHead className={`text-center ${mutedText(theme)}`}>MENTIONS</TableHead>
                <TableHead className={`text-center ${mutedText(theme)}`}>RISK</TableHead>
                <TableHead className={`text-center ${mutedText(theme)}`}>VELOCITY</TableHead>
                <TableHead className={`text-center ${mutedText(theme)}`}>SENTIMENT</TableHead>
                <TableHead className={`text-right pr-6 ${mutedText(theme)}`}>ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredNarratives.map((n, idx) => {
                const sentimentScore = n.sentiment !== undefined ? n.sentiment : 0.0;
                const statusColor = sentimentScore >= 0.25 ? "text-emerald-500" : sentimentScore <= -0.25 ? "text-red-500" : "text-amber-500";

                return (
                  <TableRow key={n.id ?? idx} className={`transition-all duration-150 ${isDark ? "border-white/[0.08] hover:bg-white/[0.03]" : "border-black/[0.06] hover:bg-black/[0.02]"}`}>
                    <TableCell className={`font-bold truncate max-w-[200px] ${bodyText(theme)}`}>{n.name}</TableCell>
                    <TableCell className="text-center"><Badge variant="outline" className={`text-xs font-normal uppercase tracking-wider ${mutedText(theme)} ${isDark ? "bg-white/[0.04] border-white/[0.12]" : "bg-black/[0.03] border-black/[0.08]"}`}>{n.type || "General"}</Badge></TableCell>
                    <TableCell className={`text-center font-bold ${bodyText(theme)}`}>{n.mentions || 0}</TableCell>
                    <TableCell className="text-center font-bold text-red-500">{Math.round(n.risk || 0)}</TableCell>
                    <TableCell className={`text-center ${bodyText(theme)}`}>{(n.trend || 0).toFixed(1)}%</TableCell>
                    <TableCell className={`text-center font-bold ${statusColor}`}>{sentimentScore.toFixed(2)}</TableCell>
                    <TableCell className="text-right pr-6">
                      <Button
                        size="sm"
                        className="bg-purple-500/10 text-purple-400 border border-purple-500/30 hover:bg-purple-600 hover:text-white font-mono text-xs h-7 px-3"
                        onClick={() => handleTraceClick(n.name)}
                      >
                        Details
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
              {filteredNarratives.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className={`text-center py-8 font-mono ${mutedText(theme)}`}>
                    No narrative clusters match the search filters.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 6. Slide-over Details Drawer */}
      {drawerData && (
        <div className={`fixed inset-y-0 right-0 z-50 w-[420px] backdrop-blur-2xl border-l shadow-2xl transform transition-transform duration-300 ease-out flex flex-col font-mono text-xs ${bodyText(theme)} ${isDark ? "bg-zinc-950/95 border-white/[0.12]" : "bg-white/95 border-black/[0.06]"}`}>
          {/* Header -- kept high-opacity for the same legibility reason as
              Risk Center's drawers: a full-height panel over dimmed content
              reads better solid than at the standard glass alpha. */}
          <div className={`flex justify-between items-center p-4 border-b ${isDark ? "border-white/[0.12] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
            <span className="uppercase tracking-wider font-bold" style={{ color: accent }}>{drawerData.type} Details</span>
            <button
              onClick={() => setDrawerData(null)}
              className={`flex items-center gap-1.5 font-bold min-h-[44px] transition-colors ${mutedText(theme)} ${isDark ? "hover:text-zinc-100" : "hover:text-zinc-900"}`}
            >
              <X className="h-5 w-5" />
              <span className="text-xs">Close</span>
            </button>
          </div>

          {/* Scrollable details area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            
            {/* CLIENT VIEW */}
            {drawerData.type === "client" && (
              <div className="space-y-4">
                <div className="space-y-1">
                  <span className="dash-muted block uppercase text-xs">Client Entity</span>
                  <span className="text-[14px] font-bold dash-strong block leading-snug">{drawerData.data.name} Corp</span>
                </div>
                
                <div className="dash-box p-3 rounded border dash-border space-y-2">
                  <div className="flex justify-between">
                    <span className="dash-muted">Reputation Metric:</span>
                    <span className="dash-accent font-bold">{drawerData.data.avgReputation} / 100</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="dash-muted">Total Monitored Executives:</span>
                    <span className="dash-strong font-bold">{drawerData.data.totalExecutives}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="dash-muted">Active Narratives:</span>
                    <span className="text-purple-400 font-bold">{drawerData.data.totalNarratives}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="dash-muted">Ingested Documents:</span>
                    <span className="dash-strong font-bold">{drawerData.data.totalDocuments}</span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="dash-muted block uppercase text-xs">Monitored Executives</span>
                  <div className="dash-box border dash-border rounded p-2 divide-y divide-[#1F2937]/30 text-xs">
                    {executives.map((exec, idx) => (
                      <div key={idx} className="flex justify-between py-1.5 first:pt-0 last:pb-0">
                        <span className="dash-strong">{exec.name}</span>
                        <span className="dash-accent font-bold">{exec.score?.toFixed(1)} [{exec.grade}]</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="dash-muted block uppercase text-xs">Active Narratives</span>
                  <div className="dash-box border dash-border rounded p-2 divide-y divide-[#1F2937]/30 text-xs">
                    {narratives.map((narr, idx) => (
                      <div key={idx} className="flex justify-between py-1.5 first:pt-0 last:pb-0">
                        <span className="dash-strong truncate max-w-[200px]">{narr.name}</span>
                        <span className="text-red-400 font-bold">{Math.round(narr.risk)} pts</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-1">
                  <span className="dash-muted block uppercase text-xs">Latest Monitored Activity</span>
                  <div className="dash-box border dash-border rounded p-2.5 text-xs dash-strong italic">
                    "{drawerData.data.latestActivity}"
                  </div>
                </div>
              </div>
            )}

            {/* EXECUTIVE VIEW */}
            {drawerData.type === "executive" && (
              <div className="space-y-4">
                <div className="space-y-1">
                  <span className="dash-muted block uppercase text-xs">Executive Profile</span>
                  <span className="text-[14px] font-bold dash-strong block leading-snug">{drawerData.data.name}</span>
                </div>

                <div className="grid grid-cols-2 gap-4 dash-box p-3 rounded border dash-border">
                  <div>
                    <span className="dash-muted block uppercase text-xs">Reputation Score</span>
                    <span className="text-[14px] font-bold dash-accent">
                      {drawerData.data.score?.toFixed(1) || "N/A"} [{drawerData.data.grade || "N/A"}]
                    </span>
                  </div>
                  <div>
                    <span className="dash-muted block uppercase text-xs">Reputation Trend</span>
                    <span className="dash-strong font-bold uppercase">{drawerData.data.reputation_trend || "STABLE"}</span>
                  </div>
                  <div>
                    <span className="dash-muted block uppercase text-xs">Confidence</span>
                    <span className="dash-strong font-bold">
                      {typeof drawerData.data.confidence_score === 'number' ? `${(drawerData.data.confidence_score * 100).toFixed(0)}%` : "85%"}
                    </span>
                  </div>
                  <div>
                    <span className="dash-muted block uppercase text-xs">Evidence Coverage</span>
                    <span className="dash-strong font-bold">
                      {typeof drawerData.data.data_coverage === 'number' ? `${(drawerData.data.data_coverage * 100).toFixed(0)}%` : "40%"}
                    </span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="dash-muted block uppercase text-xs">Connected Narratives</span>
                  {drawerData.data.connectedNarratives && drawerData.data.connectedNarratives.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {drawerData.data.connectedNarratives.map((narrName: string, idx: number) => (
                        <Badge 
                          key={idx} 
                          variant="outline" 
                          className="text-xs font-normal uppercase bg-[#A855F7]/10 border-[#A855F7]/30 text-purple-300 py-1 px-2 cursor-pointer hover:bg-[#A855F7]/25"
                          onClick={() => {
                            const found = narratives.find(n => n.name.toLowerCase() === narrName.toLowerCase());
                            if (found) {
                              const associatedDocs = documents.filter(d => 
                                (d.narrative && d.narrative.toLowerCase() === found.name.toLowerCase()) ||
                                (d.topic && found.name.toLowerCase().includes(d.topic.toLowerCase()))
                              );
                              setDrawerData({
                                type: "narrative",
                                data: {
                                  ...found,
                                  linkedExecutives: [drawerData.data.name],
                                  linkedDocuments: associatedDocs.map(d => ({
                                    id: d.id, title: d.title, risk: d.risk, sentiment: d.sentiment, source: d.source, timestamp: d.timestamp, content: d.content, extracted_entities: d.extracted_entities, processing_status: d.processing_status, entity_processing_status: d.entity_processing_status, topic_processing_status: d.topic_processing_status, sentiment_processing_status: d.sentiment_processing_status, url: d.url
                                  }))
                                }
                              });
                            }
                          }}
                        >
                          {narrName}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <div className="dash-muted text-xs italic">No directly connected narrative tracks.</div>
                  )}
                </div>
              </div>
            )}

            {/* NARRATIVE VIEW */}
            {drawerData.type === "narrative" && (
              <div className="space-y-4">
                <div className="space-y-1">
                  <span className="dash-muted block uppercase text-xs">Narrative Theme</span>
                  <span className="text-[14px] font-bold dash-strong block leading-snug">{drawerData.data.name}</span>
                </div>

                <div className="space-y-1">
                  <span className="dash-muted block uppercase text-xs">Executive Summary</span>
                  <div className="dash-box border dash-border rounded p-2.5 text-xs dash-strong leading-relaxed">
                    {drawerData.data.description || `Active media narrative track focusing on corporate governance and strategic alignment regarding ${drawerData.data.name}.`}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 dash-box p-2.5 rounded border dash-border text-center">
                  <div>
                    <span className="dash-muted block uppercase text-xs mb-0.5">Risk Score</span>
                    <span className="text-[13px] font-bold text-red-400">{Math.round(drawerData.data.risk || 0)} pts</span>
                  </div>
                  <div>
                    <span className="dash-muted block uppercase text-xs mb-0.5">Sentiment</span>
                    <span className={`text-[13px] font-bold ${
                      (drawerData.data.sentiment ?? 0) >= 0.25 ? "text-emerald-400" : (drawerData.data.sentiment ?? 0) <= -0.25 ? "text-red-400" : "text-amber-400"
                    }`}>
                      {drawerData.data.sentiment !== undefined ? drawerData.data.sentiment.toFixed(2) : "0.00"}
                    </span>
                  </div>
                  <div>
                    <span className="dash-muted block uppercase text-xs mb-0.5">Velocity</span>
                    <span className="text-[13px] font-bold text-orange-400">{(drawerData.data.trend || 0).toFixed(1)}%</span>
                  </div>
                </div>

                <div className="flex justify-between border-b dash-border py-1 text-xs">
                  <span className="dash-muted">Volume Level:</span>
                  <span className="dash-strong font-bold">{drawerData.data.mentions || 0} mentions</span>
                </div>

                <div className="space-y-1.5">
                  <span className="dash-muted block uppercase text-xs">Linked Executives</span>
                  <div className="flex flex-wrap gap-1.5">
                    {drawerData.data.linkedExecutives?.map((execName: string, idx: number) => (
                      <Badge 
                        key={idx} 
                        variant="outline" 
                        className="text-xs font-normal dash-accent-bg dash-accent-bg text-sky-300 py-0.5 px-1.5 cursor-pointer hover:dash-accent-bg"
                        onClick={() => {
                          const found = executives.find(e => e.name.toLowerCase() === execName.toLowerCase());
                          if (found) {
                            setDrawerData({
                              type: "executive",
                              data: {
                                ...found,
                                connectedNarratives: (narratives.filter(n => {
                                  const ents = n.evidence_metadata?.supporting_entities || [];
                                  return ents.includes(found.entity_id) || n.name.toLowerCase().includes(found.name.toLowerCase().split(" ")[0]);
                                })).map(n => n.name)
                              }
                            });
                          }
                        }}
                      >
                        {execName}
                      </Badge>
                    ))}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="dash-muted block uppercase text-xs">Linked Documents ({drawerData.data.linkedDocuments?.length || 0})</span>
                  {drawerData.data.linkedDocuments && drawerData.data.linkedDocuments.length > 0 ? (
                    <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
                      {drawerData.data.linkedDocuments.map((doc: any, idx: number) => (
                        <div key={idx} className="dash-box border dash-border rounded p-2 flex flex-col justify-between space-y-1 text-xs">
                          <span className="dash-strong font-bold truncate block">{doc.title}</span>
                          <div className="flex justify-between items-center text-xs dash-muted">
                            <span>Risk: <b className="text-red-400">{Math.round(doc.risk || 0)}</b></span>
                            <button 
                              onClick={() => setDrawerData({ type: "document", data: doc })}
                              className="text-purple-400 hover:text-purple-300 font-bold uppercase tracking-wider"
                            >
                              View Details
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="dash-muted text-xs italic">No linked documents found.</div>
                  )}
                </div>
              </div>
            )}

            {/* DOCUMENT VIEW */}
            {drawerData.type === "document" && (
              <div className="space-y-4">
                <div className="space-y-1">
                  <span className="dash-muted block uppercase text-xs">Headline</span>
                  <span className="text-[12px] font-bold dash-strong block leading-snug">{drawerData.data.title}</span>
                </div>

                <div className="grid grid-cols-2 gap-4 dash-box p-3 rounded border dash-border">
                  <div>
                    <span className="dash-muted block uppercase text-xs">Risk Score</span>
                    <span className="text-[14px] font-bold text-red-400">{Math.round(drawerData.data.risk || 0)}</span>
                  </div>
                  <div>
                    <span className="dash-muted block uppercase text-xs">Sentiment</span>
                    <span className={`text-[14px] font-bold ${(drawerData.data.sentiment ?? 0) >= 0.2 ? "text-emerald-400" : (drawerData.data.sentiment ?? 0) <= -0.2 ? "text-red-400" : "text-amber-400"}`}>
                      {drawerData.data.sentiment !== undefined ? drawerData.data.sentiment.toFixed(2) : "0.00"}
                    </span>
                  </div>
                  <div>
                    <span className="dash-muted block uppercase text-xs">Source Ingestion</span>
                    <span className="dash-strong font-bold">{drawerData.data.source || "RSS Feed"}</span>
                  </div>
                  <div>
                    <span className="dash-muted block uppercase text-xs">Published Date</span>
                    <span className="dash-strong font-bold block truncate">
                      {drawerData.data.timestamp ? new Date(drawerData.data.timestamp).toLocaleDateString() : "N/A"}
                    </span>
                  </div>
                </div>

                <div className="space-y-1">
                  <span className="dash-muted block uppercase text-xs">Context Snippet</span>
                  <div className="dash-box border dash-border rounded p-3 text-xs dash-strong max-h-[120px] overflow-y-auto leading-relaxed">
                    {drawerData.data.content || "No summary snippet available."}
                  </div>
                </div>

                {/* Extracted Entity references */}
                {drawerData.data.extracted_entities && drawerData.data.extracted_entities.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="dash-muted block uppercase text-xs">Extracted Entities</span>
                    <div className="flex flex-wrap gap-1.5">
                      {drawerData.data.extracted_entities.map((ent: any, idx: number) => (
                        <Badge key={idx} variant="outline" className="text-xs font-normal uppercase bg-slate-900/40 border-slate-800 dash-strong">
                          {ent.name} [{ent.entity_type}]
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Pipeline diagnostic checkpoints */}
                <div className="space-y-2 border-t dash-border pt-3">
                  <span className="dash-accent block uppercase text-xs font-bold">Processing Status</span>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between items-center dash-box p-1.5 rounded">
                      <span className="dash-muted">Processing Stage:</span>
                      <Badge className="bg-emerald-950 text-emerald-400 border border-emerald-900 text-xs uppercase">{drawerData.data.processing_status || "COMPLETE"}</Badge>
                    </div>
                    <div className="flex justify-between items-center dash-box p-1.5 rounded">
                      <span className="dash-muted">Extraction Stage:</span>
                      <span className="dash-strong font-bold uppercase">{drawerData.data.entity_processing_status || "COMPLETE"}</span>
                    </div>
                    <div className="flex justify-between items-center dash-box p-1.5 rounded">
                      <span className="dash-muted">Topic Classification:</span>
                      <span className="dash-strong font-bold uppercase">{drawerData.data.topic_processing_status || "COMPLETE"}</span>
                    </div>
                    <div className="flex justify-between items-center dash-box p-1.5 rounded">
                      <span className="dash-muted">Sentiment Evaluation:</span>
                      <span className="dash-strong font-bold uppercase">{drawerData.data.sentiment_processing_status || "COMPLETE"}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer buttons */}
          <div className={`p-4 border-t flex space-x-2 ${isDark ? "border-white/[0.12] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
            {drawerData.type === "document" && drawerData.data.url && (
              <a
                href={drawerData.data.url}
                target="_blank"
                rel="noreferrer"
                className={`flex-1 text-center py-2 rounded-lg flex items-center justify-center ${glassPrimaryButton(theme)}`}
              >
                View Original <ExternalLink className="h-3 w-3 ml-1.5" />
              </a>
            )}
            <Button
              className={`flex-1 border ${bodyText(theme)} ${isDark ? "bg-white/[0.06] hover:bg-white/[0.12] border-white/[0.12]" : "bg-black/[0.03] hover:bg-black/[0.06] border-black/[0.08]"}`}
              onClick={() => setDrawerData(null)}
            >
              Close Drawer
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
