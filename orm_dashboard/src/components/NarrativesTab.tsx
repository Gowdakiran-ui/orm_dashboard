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
      { label: "Monitored Narratives", value: totalNarratives, desc: "Active media clusters", color: "text-[#D4AF37]" },
      { label: "Tracked Leaders", value: totalExecs, desc: "Monitored corporate heads", color: "text-[#38BDF8]" },
      { label: "Scanned Documents", value: totalDocs, desc: "Pipeline document pool", color: "text-purple-400" },
      { label: "Highest Risk Narrative", value: highestRiskNarr, desc: "Requires strategic review", color: "text-red-500" },
      { label: "Fastest Growing Narrative", value: fastestGrowingNarr, desc: "High velocity trend", color: "text-orange-400" },
      { label: "Most Mentioned Executive", value: mostMentionedExec, desc: "Core voice proxy", color: "text-indigo-400" },
      { label: "Average Risk Level", value: `${avgRiskScore} pts`, desc: "Risk index across feed", color: "text-rose-450" },
      { label: "Average Strength", value: `${avgNarrativeStrength}%`, desc: "Narrative velocity rate", color: "text-emerald-400" }
    ];
  }, [documents, executives, narratives]);

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

  const cardStyle = "bg-[#060B18]/60 border-[#1F2937]/70 shadow-[inset_0_1.5px_2px_rgba(255,255,255,0.06)] hover:border-[#D4AF37]/35 hover:shadow-[0_0_20px_rgba(212,175,55,0.12)] transition-all duration-300 rounded-xl";

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
      const sentimentColor = data.sentiment >= 0.25 ? "text-emerald-400" : data.sentiment <= -0.25 ? "text-red-400" : "text-amber-400";
      return (
        <div className="bg-[#0b0f19]/95 border border-[#1F2937]/90 rounded-lg p-3 font-mono text-[10px] space-y-1.5 shadow-2xl text-slate-200">
          <div className="font-bold text-[#D4AF37] border-b border-[#1F2937] pb-1 truncate max-w-[200px] uppercase">
            {data.name}
          </div>
          <div className="flex justify-between space-x-6">
            <span className="text-slate-500">Risk Score:</span>
            <span className="text-red-400 font-bold">{data.risk} pts</span>
          </div>
          <div className="flex justify-between space-x-6">
            <span className="text-slate-500">Velocity:</span>
            <span className="text-slate-200 font-bold">{data.trend?.toFixed(1)}%</span>
          </div>
          <div className="flex justify-between space-x-6">
            <span className="text-slate-500">Sentiment:</span>
            <span className={`font-bold ${sentimentColor}`}>{data.sentiment?.toFixed(2)}</span>
          </div>
          <div className="flex justify-between space-x-6">
            <span className="text-slate-500">Volume:</span>
            <span className="text-slate-200 font-bold">{data.mentions || 0} mentions</span>
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
            className="bg-[#060B18]/60 border border-[#1F2937]/60 shadow-[inset_0_1px_2px_rgba(255,255,255,0.05)] rounded-xl p-4 flex flex-col justify-between hover:border-[#D4AF37]/30 transition-all duration-300"
          >
            <span className="text-[10px] text-slate-500 uppercase tracking-wider block mb-2">{k.label}</span>
            <div>
              <span className={`text-lg font-bold block ${k.color} truncate`}>{k.value}</span>
              <span className="text-[8.5px] text-slate-500 block truncate mt-1">{k.desc}</span>
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
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Narrative Health Bubble Matrix</CardTitle>
          </CardHeader>
          <CardContent className="h-[480px]">
            {healthMatrixData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 30, right: 60, left: 30, bottom: 50 }}>
                  <XAxis 
                    type="number" 
                    dataKey="trend" 
                    name="Velocity" 
                    stroke="#94A3B8" 
                    fontSize={14} 
                    tickLine={true}
                    label={{ value: 'Velocity Index', position: 'bottom', fill: '#94A3B8', offset: 25, fontSize: 15, fontFamily: 'monospace', fontWeight: 'bold' }} 
                  />
                  <YAxis 
                    type="number" 
                    dataKey="risk" 
                    name="Risk" 
                    stroke="#94A3B8" 
                    fontSize={14} 
                    tickLine={true}
                    label={{ value: 'Risk Score', angle: -90, position: 'left', fill: '#94A3B8', offset: 25, fontSize: 15, fontFamily: 'monospace', fontWeight: 'bold' }} 
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
              <div className="flex items-center justify-center h-full text-slate-500 font-mono text-xs">No matching narrative vectors.</div>
            )}
          </CardContent>
        </Card>

        {/* Narrative Creation Timeline */}
        <Card className={cardStyle}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Narrative Spikes Timeline</CardTitle>
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
                  <XAxis dataKey="date" stroke="#94A3B8" fontSize={9} />
                  <YAxis stroke="#94A3B8" fontSize={9} />
                  <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff', fontSize: 10, fontFamily: 'monospace' }} />
                  <Area type="monotone" dataKey="Volume" stroke="#A855F7" strokeWidth={1.8} fillOpacity={1} fill="url(#colorIngestVolume)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-500 font-mono text-xs">No historical volume markers.</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 5. Detailed Table register */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl rounded-xl">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Narrative Intelligence Table Register</CardTitle>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <Table className="font-mono text-xs">
            <TableHeader className="bg-[#030712]/80 border-b border-[#1F2937]/50">
              <TableRow className="border-b border-[#1F2937]/30 hover:bg-transparent">
                <TableHead className="w-1/4 text-slate-400">NARRATIVE THEME</TableHead>
                <TableHead className="text-slate-400 text-center">TYPE</TableHead>
                <TableHead className="text-slate-400 text-center">MENTIONS</TableHead>
                <TableHead className="text-slate-400 text-center">RISK</TableHead>
                <TableHead className="text-slate-400 text-center">VELOCITY</TableHead>
                <TableHead className="text-slate-400 text-center">SENTIMENT</TableHead>
                <TableHead className="text-slate-400 text-right pr-6">ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredNarratives.map((n, idx) => {
                const sentimentScore = n.sentiment !== undefined ? n.sentiment : 0.0;
                const statusColor = sentimentScore >= 0.25 ? "text-emerald-400" : sentimentScore <= -0.25 ? "text-red-400" : "text-amber-400";
                
                return (
                  <TableRow key={n.id ?? idx} className="border-b border-[#1F2937]/30 hover:bg-[#060B18]/30 transition-all duration-150">
                    <TableCell className="font-bold text-slate-200 truncate max-w-[200px]">{n.name}</TableCell>
                    <TableCell className="text-center"><Badge variant="outline" className="text-[9px] font-normal uppercase tracking-wider bg-slate-900/40 border-slate-800 text-slate-350">{n.type || "General"}</Badge></TableCell>
                    <TableCell className="text-center font-bold">{n.mentions || 0}</TableCell>
                    <TableCell className="text-center font-bold text-red-400">{n.risk || 0}</TableCell>
                    <TableCell className="text-center text-slate-300">{(n.trend || 0).toFixed(1)}%</TableCell>
                    <TableCell className={`text-center font-bold ${statusColor}`}>{sentimentScore.toFixed(2)}</TableCell>
                    <TableCell className="text-right pr-6">
                      <Button 
                        size="sm"
                        className="bg-purple-950/40 text-purple-400 border border-purple-900/60 hover:bg-purple-800 hover:text-white font-mono text-[9px] h-7 px-3"
                        onClick={() => handleTraceClick(n.name)}
                      >
                        TRACE
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
              {filteredNarratives.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-slate-500 font-mono">
                    No narrative clusters match the search filters.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 6. Slide-over Tactical Intelligence Drawer */}
      {drawerData && (
        <div className="fixed inset-y-0 right-0 z-50 w-[420px] bg-[#060B18]/95 border-l border-[#1F2937] shadow-2xl backdrop-blur-md transform transition-transform duration-300 ease-out flex flex-col font-mono text-xs text-slate-200">
          {/* Header */}
          <div className="flex justify-between items-center p-4 border-b border-[#1F2937] bg-[#030712]/90">
            <span className="text-[#D4AF37] uppercase tracking-wider font-bold">{drawerData.type} Intelligence Drawer</span>
            <button 
              onClick={() => setDrawerData(null)}
              className="text-slate-400 hover:text-slate-200 font-bold text-lg"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Scrollable details area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            
            {/* CLIENT VIEW */}
            {drawerData.type === "client" && (
              <div className="space-y-4">
                <div className="space-y-1">
                  <span className="text-slate-500 block uppercase text-[8px]">Client Entity</span>
                  <span className="text-[14px] font-bold text-slate-100 block leading-snug">{drawerData.data.name} Corp</span>
                </div>
                
                <div className="bg-[#030712]/50 p-3 rounded border border-[#1F2937]/40 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Reputation Metric:</span>
                    <span className="text-[#38BDF8] font-bold">{drawerData.data.avgReputation} / 100</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Total Monitored Executives:</span>
                    <span className="text-slate-200 font-bold">{drawerData.data.totalExecutives}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Active Narratives:</span>
                    <span className="text-purple-400 font-bold">{drawerData.data.totalNarratives}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Ingested Documents:</span>
                    <span className="text-slate-200 font-bold">{drawerData.data.totalDocuments}</span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="text-slate-500 block uppercase text-[8px]">Monitored Executives</span>
                  <div className="bg-[#030712] border border-[#1F2937]/50 rounded p-2 divide-y divide-[#1F2937]/30 text-[10px]">
                    {executives.map((exec, idx) => (
                      <div key={idx} className="flex justify-between py-1.5 first:pt-0 last:pb-0">
                        <span className="text-slate-350">{exec.name}</span>
                        <span className="text-[#38BDF8] font-bold">{exec.score?.toFixed(1)} [{exec.grade}]</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="text-slate-500 block uppercase text-[8px]">Active Narratives</span>
                  <div className="bg-[#030712] border border-[#1F2937]/50 rounded p-2 divide-y divide-[#1F2937]/30 text-[10px]">
                    {narratives.map((narr, idx) => (
                      <div key={idx} className="flex justify-between py-1.5 first:pt-0 last:pb-0">
                        <span className="text-slate-350 truncate max-w-[200px]">{narr.name}</span>
                        <span className="text-red-400 font-bold">{narr.risk} pts</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-1">
                  <span className="text-slate-500 block uppercase text-[8px]">Latest Monitored Activity</span>
                  <div className="bg-[#030712]/45 border border-[#1F2937]/50 rounded p-2.5 text-[10px] text-slate-300 italic">
                    "{drawerData.data.latestActivity}"
                  </div>
                </div>
              </div>
            )}

            {/* EXECUTIVE VIEW */}
            {drawerData.type === "executive" && (
              <div className="space-y-4">
                <div className="space-y-1">
                  <span className="text-slate-500 block uppercase text-[8px]">Executive Profile</span>
                  <span className="text-[14px] font-bold text-slate-100 block leading-snug">{drawerData.data.name}</span>
                </div>

                <div className="grid grid-cols-2 gap-4 bg-[#030712]/50 p-3 rounded border border-[#1F2937]/40">
                  <div>
                    <span className="text-slate-500 block uppercase text-[8px]">Reputation Score</span>
                    <span className="text-[14px] font-bold text-[#38BDF8]">
                      {drawerData.data.score?.toFixed(1) || "N/A"} [{drawerData.data.grade || "N/A"}]
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block uppercase text-[8px]">Reputation Trend</span>
                    <span className="text-slate-200 font-bold uppercase">{drawerData.data.reputation_trend || "STABLE"}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block uppercase text-[8px]">Confidence</span>
                    <span className="text-slate-200 font-bold">
                      {typeof drawerData.data.confidence_score === 'number' ? `${(drawerData.data.confidence_score * 100).toFixed(0)}%` : "85%"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block uppercase text-[8px]">Evidence Coverage</span>
                    <span className="text-slate-200 font-bold">
                      {typeof drawerData.data.data_coverage === 'number' ? `${(drawerData.data.data_coverage * 100).toFixed(0)}%` : "40%"}
                    </span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="text-slate-500 block uppercase text-[8px]">Connected Narratives</span>
                  {drawerData.data.connectedNarratives && drawerData.data.connectedNarratives.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {drawerData.data.connectedNarratives.map((narrName: string, idx: number) => (
                        <Badge 
                          key={idx} 
                          variant="outline" 
                          className="text-[9px] font-normal uppercase bg-[#A855F7]/10 border-[#A855F7]/30 text-purple-300 py-1 px-2 cursor-pointer hover:bg-[#A855F7]/25"
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
                    <div className="text-slate-500 text-[10px] italic">No directly connected narrative tracks.</div>
                  )}
                </div>
              </div>
            )}

            {/* NARRATIVE VIEW */}
            {drawerData.type === "narrative" && (
              <div className="space-y-4">
                <div className="space-y-1">
                  <span className="text-slate-500 block uppercase text-[8px]">Narrative Theme</span>
                  <span className="text-[14px] font-bold text-slate-100 block leading-snug">{drawerData.data.name}</span>
                </div>

                <div className="space-y-1">
                  <span className="text-slate-500 block uppercase text-[8px]">Executive Summary</span>
                  <div className="bg-[#030712] border border-[#1F2937]/50 rounded p-2.5 text-[10px] text-slate-350 leading-relaxed">
                    {drawerData.data.description || `Active media narrative track focusing on corporate governance and strategic alignment regarding ${drawerData.data.name}.`}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 bg-[#030712]/50 p-2.5 rounded border border-[#1F2937]/40 text-center">
                  <div>
                    <span className="text-slate-500 block uppercase text-[7.5px] mb-0.5">Risk Score</span>
                    <span className="text-[13px] font-bold text-red-400">{drawerData.data.risk || 0} pts</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block uppercase text-[7.5px] mb-0.5">Sentiment</span>
                    <span className={`text-[13px] font-bold ${
                      (drawerData.data.sentiment ?? 0) >= 0.25 ? "text-emerald-400" : (drawerData.data.sentiment ?? 0) <= -0.25 ? "text-red-400" : "text-amber-400"
                    }`}>
                      {drawerData.data.sentiment !== undefined ? drawerData.data.sentiment.toFixed(2) : "0.00"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block uppercase text-[7.5px] mb-0.5">Velocity</span>
                    <span className="text-[13px] font-bold text-orange-400">{(drawerData.data.trend || 0).toFixed(1)}%</span>
                  </div>
                </div>

                <div className="flex justify-between border-b border-[#1F2937]/35 py-1 text-[10px]">
                  <span className="text-slate-500">Volume Level:</span>
                  <span className="text-slate-200 font-bold">{drawerData.data.mentions || 0} mentions</span>
                </div>

                <div className="space-y-1.5">
                  <span className="text-slate-500 block uppercase text-[8px]">Linked Executives</span>
                  <div className="flex flex-wrap gap-1.5">
                    {drawerData.data.linkedExecutives?.map((execName: string, idx: number) => (
                      <Badge 
                        key={idx} 
                        variant="outline" 
                        className="text-[9px] font-normal bg-[#38BDF8]/10 border-[#38BDF8]/30 text-sky-300 py-0.5 px-1.5 cursor-pointer hover:bg-[#38BDF8]/25"
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
                  <span className="text-slate-500 block uppercase text-[8px]">Linked Documents ({drawerData.data.linkedDocuments?.length || 0})</span>
                  {drawerData.data.linkedDocuments && drawerData.data.linkedDocuments.length > 0 ? (
                    <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
                      {drawerData.data.linkedDocuments.map((doc: any, idx: number) => (
                        <div key={idx} className="bg-[#030712]/60 border border-[#1F2937]/50 rounded p-2 flex flex-col justify-between space-y-1 text-[10px]">
                          <span className="text-slate-200 font-bold truncate block">{doc.title}</span>
                          <div className="flex justify-between items-center text-[9px] text-slate-500">
                            <span>Risk: <b className="text-red-400">{doc.risk}</b></span>
                            <button 
                              onClick={() => setDrawerData({ type: "document", data: doc })}
                              className="text-purple-400 hover:text-purple-300 font-bold uppercase tracking-wider"
                            >
                              Open Trace
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-slate-500 text-[10px] italic">No linked documents found.</div>
                  )}
                </div>
              </div>
            )}

            {/* DOCUMENT VIEW */}
            {drawerData.type === "document" && (
              <div className="space-y-4">
                <div className="space-y-1">
                  <span className="text-slate-500 block uppercase text-[8px]">Headline</span>
                  <span className="text-[12px] font-bold text-slate-100 block leading-snug">{drawerData.data.title}</span>
                </div>

                <div className="grid grid-cols-2 gap-4 bg-[#030712]/50 p-3 rounded border border-[#1F2937]/40">
                  <div>
                    <span className="text-slate-500 block uppercase text-[8px]">Risk Score</span>
                    <span className="text-[14px] font-bold text-red-400">{drawerData.data.risk || 0}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block uppercase text-[8px]">Sentiment</span>
                    <span className={`text-[14px] font-bold ${(drawerData.data.sentiment ?? 0) >= 0.2 ? "text-emerald-400" : (drawerData.data.sentiment ?? 0) <= -0.2 ? "text-red-400" : "text-amber-400"}`}>
                      {drawerData.data.sentiment !== undefined ? drawerData.data.sentiment.toFixed(2) : "0.00"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block uppercase text-[8px]">Source Ingestion</span>
                    <span className="text-slate-200 font-bold">{drawerData.data.source || "RSS Feed"}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block uppercase text-[8px]">Published Date</span>
                    <span className="text-slate-200 font-bold block truncate">
                      {drawerData.data.timestamp ? new Date(drawerData.data.timestamp).toLocaleDateString() : "N/A"}
                    </span>
                  </div>
                </div>

                <div className="space-y-1">
                  <span className="text-slate-500 block uppercase text-[8px]">Context Snippet</span>
                  <div className="bg-[#030712] border border-[#1F2937]/50 rounded p-3 text-[10px] text-slate-350 max-h-[120px] overflow-y-auto leading-relaxed">
                    {drawerData.data.content || "No summary snippet available."}
                  </div>
                </div>

                {/* Extracted Entity references */}
                {drawerData.data.extracted_entities && drawerData.data.extracted_entities.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-slate-500 block uppercase text-[8px]">Extracted Entities</span>
                    <div className="flex flex-wrap gap-1.5">
                      {drawerData.data.extracted_entities.map((ent: any, idx: number) => (
                        <Badge key={idx} variant="outline" className="text-[9px] font-normal uppercase bg-slate-900/40 border-slate-800 text-slate-300">
                          {ent.name} [{ent.entity_type}]
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Pipeline diagnostic checkpoints */}
                <div className="space-y-2 border-t border-[#1F2937] pt-3">
                  <span className="text-[#D4AF37] block uppercase text-[9px] font-bold">Pipeline Telemetry Lineage</span>
                  <div className="space-y-1.5 text-[9px]">
                    <div className="flex justify-between items-center bg-[#030712]/40 p-1.5 rounded">
                      <span className="text-slate-500">Processing Stage:</span>
                      <Badge className="bg-emerald-950 text-emerald-400 border border-emerald-900 text-[8px] uppercase">{drawerData.data.processing_status || "COMPLETE"}</Badge>
                    </div>
                    <div className="flex justify-between items-center bg-[#030712]/40 p-1.5 rounded">
                      <span className="text-slate-500">Extraction Stage:</span>
                      <span className="text-slate-200 font-bold uppercase">{drawerData.data.entity_processing_status || "COMPLETE"}</span>
                    </div>
                    <div className="flex justify-between items-center bg-[#030712]/40 p-1.5 rounded">
                      <span className="text-slate-500">Topic Classification:</span>
                      <span className="text-slate-200 font-bold uppercase">{drawerData.data.topic_processing_status || "COMPLETE"}</span>
                    </div>
                    <div className="flex justify-between items-center bg-[#030712]/40 p-1.5 rounded">
                      <span className="text-slate-500">Sentiment Evaluation:</span>
                      <span className="text-slate-200 font-bold uppercase">{drawerData.data.sentiment_processing_status || "COMPLETE"}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer buttons */}
          <div className="p-4 border-t border-[#1F2937] bg-[#030712]/90 flex space-x-2">
            {drawerData.type === "document" && drawerData.data.url && (
              <a 
                href={drawerData.data.url} 
                target="_blank" 
                rel="noreferrer" 
                className="flex-1 bg-[#D4AF37] hover:bg-[#b8972f] text-black text-center py-2 rounded font-bold transition-all flex items-center justify-center"
              >
                View Original <ExternalLink className="h-3 w-3 ml-1.5" />
              </a>
            )}
            <Button 
              className="flex-1 bg-[#1F2937]/80 hover:bg-[#2e3e52] text-slate-200 border border-[#1F2937]"
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
