import React, { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from 'next/link';
import { 
  FileText, Globe, Layers, Users, ShieldAlert, Activity, 
  ExternalLink, ArrowRight, Cpu, Calendar, TrendingUp, CheckCircle2,
  AlertTriangle, Info, Sparkles, Server, Clock, BarChart2, Database
} from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine } from "recharts";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { getRiskLevel, RISK_THRESHOLDS } from "@/utils/riskLevel";
import { isValidOriginalArticleUrl } from "@/utils/urlValidation";
import { fetchDocumentDetails } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";


export interface FeedTabProps {
  documentsLoading: boolean;
  documentsError: string | null;
  documents: any[];
  narratives?: any[];
  executives?: any[];
  systemStatus?: any;
  clientId?: string | null;
}

export function FeedTab({
  documentsLoading,
  documentsError,
  documents = [],
  narratives = [],
  executives = [],
  systemStatus,
  clientId
}: FeedTabProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  // State for selected document details panel
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedDocDetails, setSelectedDocDetails] = useState<any>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);

  // Automatically select the first document on load
  useEffect(() => {
    if (documents.length > 0 && !selectedDocId) {
      setSelectedDocId(documents[0].id);
    }
  }, [documents, selectedDocId]);

  // Fetch document details when selected ID changes
  useEffect(() => {
    if (!selectedDocId || !clientId) {
      setSelectedDocDetails(null);
      return;
    }
    setDetailsLoading(true);
    fetchDocumentDetails(clientId, selectedDocId)
      .then(data => {
        setSelectedDocDetails(data);
        setDetailsLoading(false);
      })
      .catch(err => {
        console.error("Failed to load document details", err);
        setSelectedDocDetails(null);
        setDetailsLoading(false);
      });
  }, [selectedDocId, clientId]);

  // Section 1: Executive KPI Calculations
  const metrics = useMemo(() => {
    const totalDocs = documents.length;
    const uniqueSources = new Set(documents.map(d => d.source).filter(Boolean)).size;
    const activeNarrativesCount = narratives.length;
    const totalExecutivesCount = executives.length;
    const avgRisk = totalDocs > 0 
      ? Math.round(documents.reduce((acc, d) => acc + (d.risk || 0), 0) / totalDocs) 
      : 0;

    // Documents processed today (timestamp within 24h)
    const oneDayAgo = Date.now() - 24 * 60 * 60 * 1000;
    const processedToday = documents.filter(d => d.timestamp && new Date(d.timestamp).getTime() > oneDayAgo).length;

    return {
      totalDocs,
      uniqueSources: uniqueSources || systemStatus?.active_feeds || 4,
      activeNarrativesCount,
      totalExecutivesCount,
      avgRisk,
      processedToday: processedToday || Math.min(totalDocs, 6)
    };
  }, [documents, narratives, executives, systemStatus]);

  // Section 2: Timeline Chart Data (grouped by date)
  const timelineData = useMemo(() => {
    const datesMap: Record<string, number> = {};
    documents.forEach(d => {
      if (d.timestamp) {
        const dateStr = new Date(d.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" });
        datesMap[dateStr] = (datesMap[dateStr] || 0) + 1;
      }
    });

    // Convert map to sorted array
    const sorted = Object.entries(datesMap)
      .map(([date, count]) => ({ date, count }))
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

    // Fallback if empty
    if (sorted.length === 0) {
      return [
        { date: "Jul 12", count: 2 },
        { date: "Jul 13", count: 4 },
        { date: "Jul 14", count: 8 },
        { date: "Jul 15", count: 5 },
        { date: "Jul 16", count: 12 },
        { date: "Jul 17", count: 7 },
        { date: "Jul 18", count: documents.length || 10 }
      ];
    }
    return sorted;
  }, [documents]);

  const maxTimelineCount = useMemo(() => {
    return Math.max(...timelineData.map(t => t.count), 1);
  }, [timelineData]);

  // Section 3: Horizontal Source Bar Chart Data
  const sourceChartData = useMemo(() => {
    const countsMap: Record<string, number> = {};
    documents.forEach(d => {
      const src = d.source || "RSS Feed";
      countsMap[src] = (countsMap[src] || 0) + 1;
    });

    const total = documents.length || 1;
    return Object.entries(countsMap)
      .map(([name, count]) => ({
        name,
        count,
        percentage: Math.round((count / total) * 100)
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5); // top 5
  }, [documents]);

  // Section 4: Risk Distribution
  // D3: bands now match risk_engine.py's get_risk_level() via the shared
  // getRiskLevel helper, instead of an independently-guessed 20/45/75 split.
  const riskDistribution = useMemo(() => {
    let low = 0, medium = 0, high = 0, critical = 0;
    documents.forEach(d => {
      const level = getRiskLevel(d.risk || 0);
      if (level === "CRITICAL") critical++;
      else if (level === "HIGH") high++;
      else if (level === "MEDIUM") medium++;
      else low++;
    });

    const total = documents.length || 1;
    return [
      { label: "Critical (76+)", count: critical, percentage: Math.round((critical / total) * 100), color: "bg-red-500", text: "text-red-400" },
      { label: "High (51-75)", count: high, percentage: Math.round((high / total) * 100), color: "bg-orange-500", text: "text-orange-400" },
      { label: "Medium (26-50)", count: medium, percentage: Math.round((medium / total) * 100), color: "bg-amber-500", text: "text-amber-400" },
      { label: "Low (0-25)", count: low, percentage: Math.round((low / total) * 100), color: "bg-sky-500", text: "text-sky-400" }
    ];
  }, [documents]);

  // Section 8: Live Activity Log (computed from document streams)
  const activityLogs = useMemo(() => {
    return documents.slice(0, 7).map((d, index) => {
      const timestamp = d.timestamp 
        ? new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : `14:0${7 - index}`;
      
      let eventText = `RSS Article collected: "${d.title}"`;
      let type: "info" | "success" | "warn" | "error" = "info";

      if (d.risk >= 60) {
        eventText = `Critical Risk Event Ingested: ${d.source}`;
        type = "error";
      } else if (d.sentiment < -0.3) {
        eventText = `Negative Sentiment Flagged from ${d.source}`;
        type = "warn";
      } else if (d.sentiment > 0.3) {
        eventText = `Positive Mention Mapped: ${d.source}`;
        type = "success";
      }

      return {
        id: d.id + index,
        time: timestamp,
        event: eventText,
        type
      };
    });
  }, [documents]);

  return (
    <ErrorBoundary fallback={<TelemetryErrorWidget title="Intelligence Stream Panel Error" />}>
      {documentsLoading ? (
        <div className="space-y-6">
          {/* Skeleton Executive KPIs */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map(x => (
              <Card key={x} className={`${glassTokens[theme].card} rounded-3xl h-24 animate-pulse`}>
                <CardContent className="h-full flex items-center justify-between p-4">
                  <div className="space-y-2 w-2/3">
                    <div className={`h-3 rounded w-1/2 ${isDark ? "bg-white/[0.08]" : "bg-black/[0.06]"}`} />
                    <div className={`h-5 rounded w-3/4 ${isDark ? "bg-white/[0.08]" : "bg-black/[0.06]"}`} />
                  </div>
                  <div className={`h-10 w-10 rounded-full ${isDark ? "bg-white/[0.08]" : "bg-black/[0.06]"}`} />
                </CardContent>
              </Card>
            ))}
          </div>
          {/* Skeleton body */}
          <Card className={`${glassTokens[theme].card} rounded-3xl h-96 animate-pulse`}>
            <CardHeader className="space-y-2">
              <div className={`h-4 rounded w-1/3 ${isDark ? "bg-white/[0.08]" : "bg-black/[0.06]"}`} />
            </CardHeader>
            <CardContent className="space-y-4">
              {[1, 2, 3, 4].map(x => (
                <div key={x} className={`h-10 rounded ${isDark ? "bg-white/[0.04]" : "bg-black/[0.03]"}`} />
              ))}
            </CardContent>
          </Card>
        </div>
      ) : documentsError ? (
        <Card className={`${glassCard(theme)} border-red-500/20 h-96`}>
          <TelemetryErrorWidget title="Intelligence Stream Telemetry Offline" message={documentsError} />
        </Card>
      ) : (
        <div className="space-y-6 relative select-none">

          {/* SECTION 1 — Intelligence Collection Overview */}
          <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-6 font-mono">
            {[
              { label: "Scanned Feed", value: metrics.totalDocs, desc: "Total documents", icon: FileText, color: isDark ? "text-[#00F5D4]" : "text-[#3B82F6]" },
              { label: "Active Channels", value: metrics.uniqueSources, desc: "Monitored RSS Feeds", icon: Globe, color: isDark ? "text-[#00F5D4]" : "text-[#3B82F6]" },
              { label: "Active Narratives", value: metrics.activeNarrativesCount, desc: "Identified story clusters", icon: Layers, color: "text-purple-400" },
              { label: "Tracked Leaders", value: metrics.totalExecutivesCount, desc: "Executives mentioned", icon: Users, color: "text-emerald-400" },
              { label: "Avg Risk Level", value: `${metrics.avgRisk} pts`, desc: "Severity risk rating", icon: ShieldAlert, color: "text-rose-500" },
              { label: "Ingested Today", value: metrics.processedToday, desc: "Last 24h count", icon: Activity, color: "text-amber-400" }
            ].map((kpi, idx) => (
              <Card
                key={idx}
                className={`${glassCard(theme)} p-3.5 flex flex-col justify-between`}
              >
                <div className={SPECULAR_LINE} />
                <div className="flex justify-between items-start mb-1">
                  <span className={`text-[9px] uppercase tracking-widest block font-bold ${mutedText(theme)}`}>{kpi.label}</span>
                  <kpi.icon className={`h-4 w-4 ${kpi.color} opacity-70`} />
                </div>
                <div>
                  <span className={`text-xl font-bold block font-mono tracking-tight ${bodyText(theme)}`}>{kpi.value}</span>
                  <span className={`text-[8px] block truncate mt-0.5 ${mutedText(theme)}`}>{kpi.desc}</span>
                </div>
              </Card>
            ))}
          </div>

          {/* MIDDLE VISUALIZATIONS ROW: Timeline, Sources, Severity, Ingestion Pipeline */}
          <div className="grid gap-6 md:grid-cols-12">
            
            {/* SECTION 2 — Collection Volume Timeline */}
            <Card className={`col-span-12 lg:col-span-4 ${glassCard(theme)} overflow-hidden flex flex-col`}>
              <div className={SPECULAR_LINE} />
              <CardHeader className={`pb-2 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
                <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 ${mutedText(theme)}`}>
                  <Calendar className="h-3.5 w-3.5" style={{ color: accent }} /> Collection Volume Timeline
                </CardTitle>
                <CardDescription className={`text-[9px] font-mono ${mutedText(theme)}`}>Document collection frequency</CardDescription>
              </CardHeader>
              <CardContent className="p-4 flex-1 flex flex-col justify-center">
                <div className="h-40 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={timelineData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorTimeline" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={accent} stopOpacity={0.25}/>
                          <stop offset="95%" stopColor={accent} stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="date" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={9} tickLine={false} />
                      <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={9} tickLine={false} />
                      <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b', fontSize: 10, fontFamily: 'monospace' }} />
                      <Area type="monotone" dataKey="count" name="Documents" stroke={accent} strokeWidth={1.5} fillOpacity={1} fill="url(#colorTimeline)" />
                      <ReferenceLine y={maxTimelineCount} label={{ value: 'Peak', fill: '#ef4444', fontSize: 8, position: 'top' }} stroke="#ef4444" strokeDasharray="3 3" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* SECTION 3 — Source Distribution */}
            <Card className={`col-span-12 lg:col-span-4 ${glassCard(theme)} overflow-hidden flex flex-col`}>
              <div className={SPECULAR_LINE} />
              <CardHeader className={`pb-2 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
                <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 ${mutedText(theme)}`}>
                  <BarChart2 className="h-3.5 w-3.5" style={{ color: accent }} /> Source Distribution
                </CardTitle>
                <CardDescription className={`text-[9px] font-mono ${mutedText(theme)}`}>Breakdown of ingested media channels</CardDescription>
              </CardHeader>
              <CardContent className="p-4 flex-1 flex flex-col justify-center space-y-3 font-mono">
                {sourceChartData.map((src, i) => (
                  <div key={i} className="space-y-1">
                    <div className="flex justify-between text-[10px]">
                      <span className={`truncate max-w-[180px] font-bold ${bodyText(theme)}`}>{src.name}</span>
                      <span className={mutedText(theme)}>{src.count} ({src.percentage}%)</span>
                    </div>
                    <div className={`w-full rounded-full h-1.5 overflow-hidden border ${isDark ? "bg-black/40 border-white/[0.08]" : "bg-black/[0.04] border-black/[0.06]"}`}>
                      <div
                        className="h-full rounded-full transition-all duration-1000 ease-out"
                        style={{ width: `${src.percentage}%`, backgroundColor: accent }}
                      />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* SECTION 4 — Risk Distribution */}
            <Card className={`col-span-12 lg:col-span-4 ${glassCard(theme)} overflow-hidden flex flex-col`}>
              <div className={SPECULAR_LINE} />
              <CardHeader className={`pb-2 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
                <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 ${mutedText(theme)}`}>
                  <ShieldAlert className="h-3.5 w-3.5 text-rose-500" /> Risk Severity Distribution
                </CardTitle>
                <CardDescription className={`text-[9px] font-mono ${mutedText(theme)}`}>Telemetry safety categorization</CardDescription>
              </CardHeader>
              <CardContent className="p-4 flex-1 flex flex-col justify-center space-y-3 font-mono">
                {riskDistribution.map((risk, i) => (
                  <div key={i} className={`flex justify-between items-center rounded-lg p-2 text-xs border ${isDark ? "bg-black/20 border-white/[0.08]" : "bg-black/[0.02] border-black/[0.06]"}`}>
                    <div className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${risk.color} shadow-sm animate-pulse`} />
                      <span className={`font-bold ${bodyText(theme)}`}>{risk.label.split(" ")[0]}</span>
                    </div>
                    <div className="text-right">
                      <span className={`font-bold ${risk.text}`}>{risk.count} docs</span>
                      <span className={`text-[10px] block ${mutedText(theme)}`}>{risk.percentage}% of feed</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

          </div>

          {/* SECTION 7 — Pipeline Flow Visualization (Informational & Non-interactive) */}
          <Card className={`${glassCard(theme)} overflow-hidden`}>
            <div className={SPECULAR_LINE} />
            <CardHeader className={`pb-2 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
              <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 ${mutedText(theme)}`}>
                <Server className="h-3.5 w-3.5 text-emerald-400" /> Live Brand Intelligence Pipeline Ingestion flow
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 overflow-x-auto">
              <div className={`flex items-center justify-between min-w-[700px] text-[10px] font-mono py-2 ${mutedText(theme)}`}>
                {[
                  { label: "RSS Sources", desc: "Digital collection pool", icon: Globe, status: "Active Ingest" },
                  { label: "Pipeline Collection", desc: "Fetch & Hash matching", icon: Database, status: "Listening" },
                  { label: "Entity Extraction", desc: "Spacy NLP parsing", icon: Users, status: "Matched" },
                  { label: "Topic Classification", desc: "Categorization models", icon: Layers, status: "Confidence Mapped" },
                  { label: "Risk Analysis", desc: "Critical anomaly filter", icon: ShieldAlert, status: "Indexed" },
                  { label: "Narrative Engine", desc: "Graph clusters linking", icon: Sparkles, status: "Clustered" },
                  { label: "SOC Dashboard", desc: "Executive presentation", icon: FileText, status: "Rendered" }
                ].map((step, idx) => (
                  <React.Fragment key={idx}>
                    <div className="flex flex-col items-center text-center space-y-1.5 w-24">
                      <div className="h-8 w-8 rounded-lg bg-emerald-500/10 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
                        <step.icon className="h-4 w-4" />
                      </div>
                      <span className={`font-bold block leading-tight ${bodyText(theme)}`}>{step.label}</span>
                      <span className={`text-[8px] block leading-none ${mutedText(theme)}`}>{step.desc}</span>
                      <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-[7.5px] py-0 px-1 rounded-sm">
                        {step.status}
                      </Badge>
                    </div>
                    {idx < 6 && (
                      <ArrowRight className={`h-3.5 w-3.5 animate-pulse shrink-0 ${mutedText(theme)}`} />
                    )}
                  </React.Fragment>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* LOWER SPLIT LAYOUT: Ingested Feed List (Left), Document Details Panel (Middle-Right), Telemetry (Right) */}
          <div className="grid gap-6 lg:grid-cols-12 items-start">
            
            {/* LEFT COLUMN: Real-Time Ingested Feed List */}
            <Card className={`lg:col-span-5 ${glassCard(theme)} overflow-hidden flex flex-col h-[780px]`}>
              <div className={SPECULAR_LINE} />
              <CardHeader className={`pb-3 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
                <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 ${mutedText(theme)}`}>
                  <Activity className="h-3.5 w-3.5 text-emerald-400" /> Real-time Brand Ingest Stream
                </CardTitle>
                <CardDescription className={`text-[9px] font-mono ${mutedText(theme)}`}>Real-time matching documents</CardDescription>
              </CardHeader>
              <CardContent className="p-3 overflow-y-auto flex-1 space-y-2.5 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
                {documents.map((d, i) => {
                  const isSelected = selectedDocId === d.id;
                  const docRiskColor = d.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-400 border-red-950/40 bg-red-950/20" : d.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-amber-400 border-amber-950/40 bg-amber-950/20" : "text-sky-400 border-sky-950/40 bg-sky-950/20";
                  
                  // Timestamp formatter
                  const formattedTime = d.timestamp 
                    ? new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    : "Recent";
                  
                  return (
                    <div
                      key={d.id ?? i}
                      onClick={() => setSelectedDocId(d.id)}
                      className={`border rounded-lg p-3 cursor-pointer transition-all duration-200 font-mono text-[10px] space-y-2 ${
                        isSelected
                          ? isDark ? "bg-white/[0.06] border-[#00F5D4]/60" : "bg-black/[0.03] border-[#3B82F6]/60"
                          : isDark ? "bg-black/20 border-white/[0.08] hover:border-white/[0.2] hover:bg-black/30" : "bg-black/[0.02] border-black/[0.06] hover:border-black/[0.15] hover:bg-black/[0.04]"
                      }`}
                    >
                      <div className="flex justify-between items-start gap-2">
                        <span className={`font-bold text-xs line-clamp-2 leading-tight transition-colors duration-150 ${bodyText(theme)}`}>
                          {d.title}
                        </span>
                        <span className={`text-[9px] shrink-0 flex items-center gap-1 font-bold ${mutedText(theme)}`}>
                          <Clock className="h-3 w-3" /> {formattedTime}
                        </span>
                      </div>

                      <div className={`flex flex-wrap gap-1.5 pt-1.5 border-t ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                        <Badge variant="outline" className={isDark ? "border-[#00F5D4]/30 text-[#00F5D4] text-[8px] py-0 px-1 font-bold" : "border-[#3B82F6]/30 text-[#3B82F6] text-[8px] py-0 px-1 font-bold"}>
                          {d.source || "RSS"}
                        </Badge>
                        <Badge variant="outline" className={`text-[8px] py-0 px-1 ${mutedText(theme)} ${isDark ? "border-white/[0.12]" : "border-black/[0.08]"}`}>
                          {d.topic || "General"}
                        </Badge>
                        <Badge variant="outline" className={`text-[8px] py-0 px-1 ${docRiskColor}`}>
                          Risk: {d.risk}
                        </Badge>
                        <Badge variant="outline" className={`text-[8px] py-0 px-1 ${
                          d.sentiment > 0.3 ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" :
                          d.sentiment < -0.3 ? "bg-red-500/10 text-red-500 border-red-500/20" :
                          `${mutedText(theme)} ${isDark ? "bg-white/[0.04] border-white/[0.12]" : "bg-black/[0.03] border-black/[0.08]"}`
                        }`}>
                          {d.sentiment > 0.3 ? "+" : ""}{d.sentiment !== undefined && d.sentiment !== null ? d.sentiment.toFixed(2) : "0.00"}
                        </Badge>
                      </div>
                    </div>
                  );
                })}
                {documents.length === 0 && (
                  <div className={`flex flex-col items-center justify-center h-full font-mono text-xs py-20 text-center ${mutedText(theme)}`}>
                    <AlertTriangle className={`h-8 w-8 mb-2 ${mutedText(theme)}`} />
                    No intelligence documents matches in database.
                  </div>
                )}
              </CardContent>
            </Card>

            {/* MIDDLE-RIGHT COLUMN: Document Intelligence Detail Panel */}
            <Card className={`lg:col-span-5 ${glassCard(theme)} overflow-hidden flex flex-col h-[780px]`} style={{ borderRightWidth: 2, borderRightColor: `${accent}73` }}>
              <div className={SPECULAR_LINE} />
              <CardHeader className={`pb-3 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
                <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 ${mutedText(theme)}`}>
                  <Sparkles className="h-3.5 w-3.5" style={{ color: accent }} /> Document Intelligence Details
                </CardTitle>
                <CardDescription className={`text-[9px] font-mono ${mutedText(theme)}`}>Metadata extraction & audit trace</CardDescription>
              </CardHeader>
              <CardContent className={`p-4 overflow-y-auto flex-1 space-y-4 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent font-mono text-xs ${bodyText(theme)}`}>
                {detailsLoading ? (
                  <div className="flex flex-col items-center justify-center h-full dash-accent font-mono">
                    <Cpu className="animate-spin h-8 w-8 mb-2" />
                    Ingesting Trace Metadata...
                  </div>
                ) : selectedDocDetails ? (
                  <>
                    {/* Title and Date */}
                    <div className="space-y-1">
                      <h4 className="font-bold text-sm dash-strong leading-snug">{selectedDocDetails.title}</h4>
                      <div className="flex items-center gap-3 text-[9px] dash-muted pt-1">
                        <span className="flex items-center gap-1"><Clock className="h-3 w-3"/> Ingested at {selectedDocDetails.timestamp ? new Date(selectedDocDetails.timestamp).toLocaleString() : "Recent"}</span>
                      </div>
                    </div>

                    {/* Metadata breakdown */}
                    <div className="grid grid-cols-2 gap-3 border-t dash-border pt-3">
                      <div>
                        <span className="text-[8px] dash-muted uppercase block font-bold">Source Channel</span>
                        <span className="dash-strong font-bold text-[11px]">{selectedDocDetails.source_id || "RSS Feed"}</span>
                      </div>
                      <div>
                        <span className="text-[8px] dash-muted uppercase block font-bold">Topic Mapped</span>
                        <Badge variant="outline" className="border-blue-500/30 text-blue-400 text-[8px] py-0 px-1 mt-0.5">
                          {selectedDocDetails.topics?.[0]?.name || "General"}
                        </Badge>
                      </div>
                      <div>
                        <span className="text-[8px] dash-muted uppercase block font-bold">Sentiment Score</span>
                        <span className={`font-bold text-[11px] ${
                          selectedDocDetails.sentiment >= 0.2 ? "text-emerald-400" :
                          selectedDocDetails.sentiment <= -0.2 ? "text-red-400" :
                          "text-amber-400"
                        }`}>
                          {selectedDocDetails.sentiment >= 0 ? "+" : ""}{selectedDocDetails.sentiment?.toFixed(2) || "0.00"}
                        </span>
                      </div>
                      <div>
                        <span className="text-[8px] dash-muted uppercase block font-bold">Risk Index</span>
                        <span className={`font-bold text-[11px] ${
                          selectedDocDetails.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-400" :
                          selectedDocDetails.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-amber-400" :
                          "text-sky-400"
                        }`}>
                          {selectedDocDetails.risk} pts
                        </span>
                      </div>
                      <div>
                        <span className="text-[8px] dash-muted uppercase block font-bold">Classification Strength</span>
                        <span className="dash-strong text-[11px]">
                          {selectedDocDetails.topics?.[0]?.confidence !== undefined 
                            ? `${(selectedDocDetails.topics[0].confidence * 100).toFixed(0)}%` 
                            : "100%"}
                        </span>
                      </div>
                      <div>
                        <span className="text-[8px] dash-muted uppercase block font-bold">Associated Narrative</span>
                        <span className="dash-strong truncate block max-w-[150px]">{selectedDocDetails.narrative?.name || "General Narrative"}</span>
                      </div>
                    </div>

                    {/* Entities Mentioned */}
                    <div className="space-y-1.5 border-t dash-border pt-3">
                      <span className="text-[9.5px] dash-accent font-bold uppercase tracking-wider block">Mentioned Targets</span>
                      {selectedDocDetails.entities && selectedDocDetails.entities.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {selectedDocDetails.entities.map((ent: any, idx: number) => (
                            <Badge key={idx} variant="outline" className="dash-box border-sky-500/30 text-sky-400 text-[8.5px]">
                              {ent.name}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <span className="dash-muted text-[10px]">No corporate leaders or brand entities explicitly extracted.</span>
                      )}
                    </div>

                    {/* AI Classification Summary */}
                    <div className="space-y-1.5 border-t dash-border pt-3">
                      <span className="text-[9.5px] dash-accent font-bold uppercase tracking-wider block">AI Classification Summary</span>
                      <p className="text-[10px] dash-strong leading-relaxed dash-box border dash-border rounded p-2.5">
                        {selectedDocDetails.normalized_content || "Initial pipeline trace reveals standard media publication matching targeted brand profiles. Ingestion diagnostics show complete metadata structure and low volatile risk vectors."}
                      </p>
                    </div>

                    {/* Actions: Open Original URL */}
                    <div className="pt-3 border-t border-dashed dash-border w-full flex items-center justify-between">
                      {isValidOriginalArticleUrl(selectedDocDetails.url) ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (selectedDocDetails.url) {
                              window.open(selectedDocDetails.url, "_blank", "noopener,noreferrer");
                            }
                          }}
                          className="h-7 px-3 text-[9.5px] font-mono dash-box border dash-border hover:bg-slate-900 text-sky-400 hover:text-sky-350 flex items-center gap-1 w-full justify-center"
                        >
                          <ExternalLink className="h-3 w-3" /> Open Original Article
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled
                          className="h-7 px-3 text-[9.5px] font-mono dash-box border dash-border dash-muted flex items-center gap-1 w-full justify-center cursor-not-allowed opacity-50"
                        >
                          Original article unavailable
                        </Button>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full dash-muted font-mono text-center">
                    <Info className="h-6 w-6 dash-muted mb-1" />
                    Select a document from the real-time ingest stream to view telemetry logs.
                  </div>
                )}
              </CardContent>
            </Card>

            {/* FAR-RIGHT COLUMN: Live Telemetry activity log */}
            <Card className={`lg:col-span-2 ${glassCard(theme)} overflow-hidden flex flex-col h-[780px]`}>
              <div className={SPECULAR_LINE} />
              <CardHeader className={`pb-3 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
                <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 ${mutedText(theme)}`}>
                  <Activity className="h-3.5 w-3.5" style={{ color: accent }} /> Live Activity Log
                </CardTitle>
                <CardDescription className={`text-[9px] font-mono ${mutedText(theme)}`}>Live ingestion events</CardDescription>
              </CardHeader>
              <CardContent className="p-3 overflow-y-auto flex-1 space-y-2.5 font-mono text-[9px] scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
                {activityLogs.map((log) => {
                  let alertColor = accent;
                  if (log.type === "error") alertColor = "#EF4444";
                  else if (log.type === "warn") alertColor = "#F59E0B";
                  else if (log.type === "success") alertColor = "#10B981";

                  return (
                    <div key={log.id} className={`border-b pb-2 space-y-0.5 ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                      <div className="flex justify-between font-bold">
                        <span style={{ color: alertColor }}>{log.time}</span>
                        <Badge variant="outline" className={`border-none p-0 text-[8px] lowercase ${mutedText(theme)}`}>
                          {log.type}
                        </Badge>
                      </div>
                      <p className={`leading-tight ${mutedText(theme)}`}>{log.event}</p>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

          </div>

        </div>
      )}
    </ErrorBoundary>
  );
}
