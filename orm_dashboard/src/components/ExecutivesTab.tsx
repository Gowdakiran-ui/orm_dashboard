import React, { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { 
  LineChart as RechartsLineChart, Line, XAxis, YAxis, 
  CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, AreaChart, Area 
} from 'recharts';
import { 
  Users, Activity, Search, AlertTriangle, ShieldCheck, Trophy, Info, 
  TrendingUp, Calendar, AlertOctagon, X, ExternalLink, Award
} from "lucide-react";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";
import { fetchDocumentDetails } from "@/lib/api";

export interface ExecutivesTabProps {
  execHistoryLoading: boolean;
  execHistory: Record<string, any[]>;
  execTrendChartData: any[];
  executivesLoading: boolean;
  executivesError: string | null;
  executives: any[];
  lastProcessedTimestamp: string;
  documents: any[];
  narratives: any[];
  clientId?: string | null;
}

export function ExecutivesTab({
  execHistoryLoading,
  execHistory,
  execTrendChartData,
  executivesLoading,
  executivesError,
  executives,
  lastProcessedTimestamp,
  documents,
  narratives,
  clientId
}: ExecutivesTabProps) {
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  // The /documents/client/{id} list (source of `documents`) doesn't include
  // `url` -- fetch it per-selection the same way FeedTab does, since the
  // single-document detail endpoint does return it.
  const [selectedDocUrl, setSelectedDocUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedDocId || !clientId) {
      setSelectedDocUrl(null);
      return;
    }
    let cancelled = false;
    fetchDocumentDetails(clientId, selectedDocId)
      .then(details => { if (!cancelled) setSelectedDocUrl(details?.url || null); })
      .catch(() => { if (!cancelled) setSelectedDocUrl(null); });
    return () => { cancelled = true; };
  }, [selectedDocId, clientId]);

  // 1. EXECUTIVE NAMES CACHE
  const execNames = useMemo(() => {
    return (executives || []).map(e => e.name.toLowerCase());
  }, [executives]);

  // 2. FILTER EXECUTIVE-RELATED PIPELINE EVENTS
  const execEvents = useMemo(() => {
    return (documents || [])
      .filter(d => {
        if (!d) return false;
        const docText = (d.title || "") + " " + (d.original_content || "");
        const matchesName = execNames.some(name => docText.toLowerCase().includes(name));
        const matchesEntity = d.extracted_entities?.some((e: any) => 
          e.entity_type === "executive" || execNames.includes(e.name.toLowerCase())
        );
        return matchesName || matchesEntity;
      })
      .map(d => {
        const docText = (d.title || "") + " " + (d.original_content || "");
        const matchedExec = (executives || []).find(e => 
          docText.toLowerCase().includes(e.name.toLowerCase()) ||
          d.extracted_entities?.some((ent: any) => ent.name.toLowerCase() === e.name.toLowerCase())
        );
        return {
          ...d,
          matchedExecutive: matchedExec ? matchedExec.name : "Executive Figure",
          matchedExecObj: matchedExec
        };
      })
      .sort((a, b) => {
        const dateA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
        const dateB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
        return dateB - dateA;
      });
  }, [documents, execNames, executives]);

  const selectedDoc = useMemo(() => {
    if (!selectedDocId) return null;
    return execEvents.find(d => d.id === selectedDocId) || null;
  }, [selectedDocId, execEvents]);

  // 3. EXECUTIVE INTEL SUMMARY METRICS
  const summary = useMemo(() => {
    const totalMonitored = executives.length;
    if (totalMonitored === 0) {
      return {
        totalMonitored: 0,
        highestRep: "Insufficient historical data",
        highestRisk: "Insufficient historical data",
        mostMentioned: "Insufficient historical data",
        avgRep: "0.0",
        latestEvent: "Insufficient historical data"
      };
    }

    // Highest Reputation Executive
    const sortedByRep = [...executives].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    const highestRep = sortedByRep[0] ? `${sortedByRep[0].name} (${sortedByRep[0].score.toFixed(1)})` : "N/A";

    // Highest Risk Executive (highest avg document risk)
    const execRisks: Record<string, { totalRisk: number, count: number }> = {};
    execEvents.forEach(e => {
      if (!execRisks[e.matchedExecutive]) {
        execRisks[e.matchedExecutive] = { totalRisk: 0, count: 0 };
      }
      execRisks[e.matchedExecutive].totalRisk += e.risk ?? 0;
      execRisks[e.matchedExecutive].count += 1;
    });
    let highestRiskName = "N/A";
    let highestRiskVal = -1;
    Object.entries(execRisks).forEach(([name, data]) => {
      const avg = data.totalRisk / data.count;
      if (avg > highestRiskVal) {
        highestRiskVal = avg;
        highestRiskName = `${name} (Avg Risk: ${avg.toFixed(0)})`;
      }
    });

    // Most Mentioned Executive
    const mentions: Record<string, number> = {};
    execEvents.forEach(e => {
      mentions[e.matchedExecutive] = (mentions[e.matchedExecutive] || 0) + 1;
    });
    const mostMentionedName = Object.entries(mentions).sort((a, b) => b[1] - a[1])[0]?.[0] || "N/A";

    // Average Executive Reputation Score
    const avgRepVal = executives.reduce((sum, e) => sum + (e.score ?? 0), 0) / totalMonitored;

    // Latest Executive Event
    const latestEvent = execEvents[0]?.timestamp 
      ? new Date(execEvents[0].timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
      : "Insufficient historical data";

    return {
      totalMonitored,
      highestRep,
      highestRisk: highestRiskName,
      mostMentioned: mostMentionedName,
      avgRep: avgRepVal.toFixed(1),
      latestEvent
    };
  }, [executives, execEvents]);

  // 4. SCORE DISTRIBUTION DATA
  const distributionData = useMemo(() => {
    let excellent = 0;
    let good = 0;
    let average = 0;
    let poor = 0;

    executives.forEach(e => {
      const s = e.score ?? 0;
      if (s >= 80) excellent++;
      else if (s >= 60) good++;
      else if (s >= 40) average++;
      else poor++;
    });

    return [
      { range: "Excellent (80+)", count: excellent },
      { range: "Good (60-80)", count: good },
      { range: "Average (40-60)", count: average },
      { range: "Poor (<40)", count: poor }
    ];
  }, [executives]);

  // 5. SENTIMENT BREAKDOWN DATA
  const sentimentData = useMemo(() => {
    let positive = 0;
    let neutral = 0;
    let negative = 0;

    execEvents.forEach(e => {
      const score = e.sentiment_score !== undefined ? parseFloat(e.sentiment_score) : 0;
      if (score > 0.25) positive++;
      else if (score < -0.25) negative++;
      else neutral++;
    });

    return [
      { name: "Positive", value: positive, fill: "#10B981" },
      { name: "Neutral", value: neutral, fill: "#64748B" },
      { name: "Negative", value: negative, fill: "#EF4444" }
    ];
  }, [execEvents]);

  // 6. ACTIVITY TIMELINE DATA (Aggregated by day)
  const timelineData = useMemo(() => {
    const dates: Record<string, number> = {};
    // Last 10 days structure
    for (let i = 9; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const str = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      dates[str] = 0;
    }

    execEvents.forEach(e => {
      if (e.timestamp) {
        const str = new Date(e.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        if (dates[str] !== undefined) {
          dates[str]++;
        }
      }
    });

    return Object.entries(dates).map(([date, count]) => ({ date, Mentions: count }));
  }, [execEvents]);

  // 7. EXECUTIVE INFLUENCE RANKING
  const influenceData = useMemo(() => {
    const mentions: Record<string, number> = {};
    executives.forEach(e => {
      mentions[e.name] = 0;
    });
    execEvents.forEach(e => {
      if (mentions[e.matchedExecutive] !== undefined) {
        mentions[e.matchedExecutive]++;
      }
    });
    return Object.entries(mentions)
      .map(([name, count]) => ({ name, Mentions: count }))
      .sort((a, b) => b.Mentions - a.Mentions);
  }, [executives, execEvents]);

  return (
    <div className="space-y-6">
      
      {/* 1. EXECUTIVE INTELLIGENCE SUMMARY SECTION */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl font-mono">
        <CardHeader className="pb-3 border-b border-[#1F2937]/40">
          <CardTitle className="text-xs uppercase tracking-wider text-slate-400 flex items-center">
            <Trophy className="h-4 w-4 text-[#D4AF37] mr-2" />
            Executive Intelligence Summary
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 grid gap-4 sm:grid-cols-2 md:grid-cols-6 text-[10px]">
          <div>
            <span className="text-slate-500 block">Executives Monitored:</span>
            <span className="text-slate-200 font-bold">{summary.totalMonitored}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Highest Reputation:</span>
            <span className="text-slate-200 font-bold">{summary.highestRep}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Highest Risk Executive:</span>
            <span className="text-slate-200 font-bold">{summary.highestRisk}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Most Mentioned Executive:</span>
            <span className="text-slate-200 font-bold">{summary.mostMentioned}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Average Reputation:</span>
            <span className="text-slate-200 font-bold">{summary.avgRep}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Latest Executive Event:</span>
            <span className="text-slate-200 font-bold">{summary.latestEvent}</span>
          </div>
        </CardContent>
      </Card>

      {/* 2. Executive History Line Chart */}
      <ErrorBoundary fallback={<TelemetryErrorWidget title="Exec History Chart Error" />}>
        {execHistoryLoading ? (
          <Card className="bg-[#060B18]/60 border-[#1F2937]/60 h-[340px] animate-pulse" />
        ) : (
          <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
            <CardHeader>
              <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Leadership Figures Reputation Trend</CardTitle>
              <CardDescription className="text-[10px] font-mono text-slate-500">Historical reputation score timeline per executive figure</CardDescription>
            </CardHeader>
            <CardContent className="pl-2">
              <div className="h-[280px]">
                {Object.keys(execHistory).length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <RechartsLineChart data={execTrendChartData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                      <XAxis dataKey="date" stroke="#94A3B8" fontSize={10} />
                      <YAxis stroke="#94A3B8" fontSize={10} domain={[0, 100]} />
                      <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff' }} />
                      {Object.keys(execHistory).map((name, idx) => {
                        const colors = ["#38BDF8", "#EF4444", "#EAB308", "#10B981"];
                        const col = colors[idx % colors.length];
                        return (
                          <Line key={idx} type="monotone" dataKey={name} stroke={col} strokeWidth={2} dot={{ r: 3 }} />
                        );
                      })}
                    </RechartsLineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full space-y-4">
                    <div className="grid grid-cols-2 gap-4 w-full px-8">
                      <div className="border border-[#1F2937]/60 bg-[#030712] rounded p-4 flex flex-col items-center justify-center space-y-2">
                        <Users className="h-6 w-6 text-slate-500 mb-1" />
                        <span className="font-mono text-xs text-slate-400">Total Monitored Executives</span>
                        <span className="font-mono text-xl font-bold text-slate-200">{executives.length}</span>
                      </div>
                      <div className="border border-[#1F2937]/60 bg-[#030712] rounded p-4 flex flex-col items-center justify-center space-y-2">
                        <Activity className="h-6 w-6 text-[#D4AF37]/50 mb-1" />
                        <span className="font-mono text-xs text-slate-400">Telemetry Status</span>
                        <Badge className="bg-[#D4AF37]/10 text-[#D4AF37] border border-[#D4AF37]/30 text-[9px] font-mono">GATHERING</Badge>
                      </div>
                    </div>
                    <p className="text-slate-500 font-mono text-[10px] mt-4 uppercase">Waiting for sufficient chronological data points to plot trend</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </ErrorBoundary>

      {/* 3. DUAL-ROW VISUALIZATIONS SECTION */}
      <div className="grid gap-6 md:grid-cols-2">
        
        {/* Executive Reputation Distribution */}
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
          <CardHeader>
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
              <Award className="h-4 w-4 text-[#D4AF37] mr-2" />
              Reputation Distribution
            </CardTitle>
            <CardDescription className="text-[10px] font-mono text-slate-500">Executives categorized by reputation tiers</CardDescription>
          </CardHeader>
          <CardContent className="h-[220px] pl-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distributionData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#1F2937" strokeOpacity={0.2} />
                <XAxis type="number" stroke="#94A3B8" fontSize={10} />
                <YAxis type="category" dataKey="range" stroke="#94A3B8" fontSize={10} width={100} />
                <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff' }} />
                <Bar dataKey="count" fill="#EAB308" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Executive Sentiment Breakdown */}
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
          <CardHeader>
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
              <Activity className="h-4 w-4 text-emerald-400 mr-2" />
              Executive Sentiment breakdown
            </CardTitle>
            <CardDescription className="text-[10px] font-mono text-slate-500">Sentiment classification counts across matched executive events</CardDescription>
          </CardHeader>
          <CardContent className="h-[220px] pl-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sentimentData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                <XAxis dataKey="name" stroke="#94A3B8" fontSize={10} />
                <YAxis stroke="#94A3B8" fontSize={10} />
                <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff' }} />
                <Bar dataKey="value" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Executive Activity Timeline */}
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
          <CardHeader>
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
              <Calendar className="h-4 w-4 text-[#38BDF8] mr-2" />
              Executive Activity Timeline
            </CardTitle>
            <CardDescription className="text-[10px] font-mono text-slate-500">Chronological pipeline document volume mentioning leaders</CardDescription>
          </CardHeader>
          <CardContent className="h-[220px] pl-2">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timelineData}>
                <defs>
                  <linearGradient id="colorMentions" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38BDF8" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#38BDF8" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                <XAxis dataKey="date" stroke="#94A3B8" fontSize={10} />
                <YAxis stroke="#94A3B8" fontSize={10} />
                <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff' }} />
                <Area type="monotone" dataKey="Mentions" stroke="#38BDF8" fillOpacity={1} fill="url(#colorMentions)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Executive Influence Ranking */}
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
          <CardHeader>
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
              <Users className="h-4 w-4 text-purple-400 mr-2" />
              Executive Influence Ranking
            </CardTitle>
            <CardDescription className="text-[10px] font-mono text-slate-500">Leadership figures ranked by total document mentions</CardDescription>
          </CardHeader>
          <CardContent className="h-[220px] pl-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={influenceData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#1F2937" strokeOpacity={0.2} />
                <XAxis type="number" stroke="#94A3B8" fontSize={10} />
                <YAxis type="category" dataKey="name" stroke="#94A3B8" fontSize={10} width={100} />
                <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff' }} />
                <Bar dataKey="Mentions" fill="#A855F7" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

      </div>

      {/* 4. LEADERSHIP FIGURES REPUTATION SCORECARD */}
      <ErrorBoundary fallback={<TelemetryErrorWidget title="Executives Error" />}>
        {executivesLoading ? (
          <Card className="bg-[#060B18]/60 border-[#1F2937]/60 h-48 animate-pulse" />
        ) : executivesError ? (
          <Card className="bg-[#060B18]/60 border-red-500/20 h-48">
            <TelemetryErrorWidget title="Executives Telemetry Offline" message={executivesError} />
          </Card>
        ) : (
          <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
            <CardHeader>
              <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
                <Users className="h-4 w-4 text-[#D4AF37] mr-2" />
                LEADERSHIP FIGURES REPUTATION SCORECARD
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader className="border-[#1F2937]/40 bg-[#030712]/40">
                  <TableRow className="border-[#1F2937]/40">
                    <TableHead className="text-slate-500 font-mono text-[10px]">EXECUTIVE NAME</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center">REPUTATION SCORE</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center">CONFIDENCE</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center">EVIDENCE COVERAGE</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center">TREND</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px]">TOP POSITIVE THEME</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px]">TOP NEGATIVE THEME</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {executives.map((e, i) => (
                    <TableRow key={e.id ?? i} className="border-[#1F2937]/40 hover:bg-[#060B18] transition-colors">
                      <TableCell className="font-mono text-xs font-bold text-slate-200">{e.name}</TableCell>
                      <TableCell className="text-center font-mono text-xs font-black text-[#D4AF37]">
                        {e.score !== undefined && e.score !== null ? e.score.toFixed(1) : 'N/A'}
                      </TableCell>
                      <TableCell className="text-center font-mono text-xs text-slate-350">
                        {e.confidence_score !== undefined ? `${(e.confidence_score * 100).toFixed(0)}%` : "100%"}
                        {e.health_status === 'PARTIAL' && (
                          <Badge className="ml-1.5 text-[8px] font-mono bg-amber-500/10 text-amber-400 border border-amber-500/30">
                            LIMITED DATA
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-center font-mono text-xs text-slate-350">
                        {e.data_coverage !== undefined ? `${(e.data_coverage * 100).toFixed(0)}%` : "40%"}
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge className={`text-[9px] font-mono ${
                          e.trend === 'IMPROVING' ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30" :
                          e.trend === 'DECLINING' ? "bg-red-500/10 text-red-400 border border-red-500/30" :
                          "bg-slate-500/10 text-slate-300 border border-slate-500/30"
                        }`}>
                          {e.trend ?? 'STABLE'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-emerald-400 font-mono text-xs truncate max-w-[120px]">{e.top_positive ?? 'None'}</TableCell>
                      <TableCell className="text-red-400 font-mono text-xs truncate max-w-[120px]">{e.top_negative ?? 'None'}</TableCell>
                    </TableRow>
                  ))}
                  {executives.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-10">
                        <div className="flex flex-col items-center space-y-3">
                          <Users className="h-8 w-8 text-slate-500" />
                          <p className="text-slate-400 font-mono text-sm">Executive intelligence is still being collected.</p>
                          <div className="text-slate-600 font-mono text-[9px] mt-2">
                            Last Processing: {lastProcessedTimestamp}
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </ErrorBoundary>

      {/* 5. EXECUTIVE INTELLIGENCE REGISTER */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
        <CardHeader>
          <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <div className="flex items-center">
              <Search className="h-4 w-4 text-[#38BDF8] mr-2" />
              EXECUTIVE INTELLIGENCE REGISTER
            </div>
            <Badge className="bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30 font-mono text-[9px]">
              {execEvents.length} Events
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader className="border-[#1F2937]/40 bg-[#030712]/40">
              <TableRow className="border-[#1F2937]/40">
                <TableHead className="text-slate-500 font-mono text-[10px]">EXECUTIVE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px]">EVENT HEADLINE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">BUSINESS TOPIC</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">SENTIMENT</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">REPUTATION IMPACT</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">RISK SCORE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px]">SOURCE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px]">PUBLISHED DATE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-right">ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {execEvents.map((doc, idx) => (
                <TableRow key={doc.id} className="border-[#1F2937]/40 hover:bg-[#060B18] transition-colors cursor-pointer" onClick={() => setSelectedDocId(doc.id)}>
                  <TableCell className="font-mono text-xs text-slate-200 font-bold">{doc.matchedExecutive}</TableCell>
                  <TableCell className="font-mono text-xs text-slate-300 max-w-[240px] truncate">{doc.title}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className="border-[#D4AF37]/30 text-[#D4AF37] font-mono text-[9px] bg-[#D4AF37]/5">
                      {doc.topic}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-center font-mono text-xs text-slate-300">
                    {doc.sentiment_score !== undefined ? parseFloat(doc.sentiment_score).toFixed(2) : "0.00"}
                  </TableCell>
                  <TableCell className={`text-center font-mono text-xs font-bold ${
                    parseFloat(doc.reputation_impact) >= 0 ? "text-emerald-500" : "text-red-500"
                  }`}>
                    {doc.reputation_impact}
                  </TableCell>
                  <TableCell className={`text-center font-mono text-xs font-bold ${
                    doc.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-500" : doc.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-orange-500" : "text-yellow-500"
                  }`}>
                    {doc.risk}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-slate-450 truncate max-w-[100px]">{doc.source}</TableCell>
                  <TableCell className="font-mono text-[10px] text-slate-500">
                    {doc.timestamp ? new Date(doc.timestamp).toLocaleDateString(undefined, { dateStyle: 'short' }) : "N/A"}
                  </TableCell>
                  <TableCell className="text-right">
                    <button 
                      onClick={(e) => { e.stopPropagation(); setSelectedDocId(doc.id); }}
                      className="bg-blue-600 hover:bg-blue-700 cursor-pointer text-white font-mono text-[9px] rounded py-1 px-2.5"
                    >
                      TRACE
                    </button>
                  </TableCell>
                </TableRow>
              ))}
              {execEvents.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-10 text-slate-500 font-mono text-xs">
                    No verified executive events recorded.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Slide-Over Tactical Trace Examiner Drawer */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 overflow-hidden font-mono">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setSelectedDocId(null)} />
          <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
            <div className="w-[600px] bg-[#060B18] border-l border-[#1F2937]/80 text-slate-200 flex flex-col justify-between shadow-2xl animate-in slide-in-from-right duration-300">
              
              {/* Header */}
              <div className="p-6 border-b border-[#1F2937]/80 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <AlertOctagon className="h-5 w-5 text-red-500" />
                  <span className="text-sm font-bold uppercase text-[#D4AF37]">Tactical Trace Examiner</span>
                </div>
                <button onClick={() => setSelectedDocId(null)} className="text-slate-500 hover:text-slate-200 transition-colors">
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Content Panel */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                
                {/* Headline & Meta */}
                <div className="space-y-2">
                  <h3 className="text-sm font-bold text-slate-100 leading-snug">{selectedDoc.title}</h3>
                  <div className="flex flex-wrap gap-2 text-[10px]">
                    <span className="bg-[#030712] border border-[#1F2937]/65 px-2 py-0.5 rounded text-slate-400">Source: {selectedDoc.source}</span>
                    <span className="bg-[#030712] border border-[#1F2937]/65 px-2 py-0.5 rounded text-slate-400">Topic: {selectedDoc.topic}</span>
                    <span className="bg-[#030712] border border-[#1F2937]/65 px-2 py-0.5 rounded text-slate-400">Executive: {selectedDoc.matchedExecutive}</span>
                  </div>
                </div>

                {/* Risk & Sentiment score calculations */}
                <div className="bg-[#030712] p-4 rounded border border-red-500/20 space-y-3">
                  <div className="flex justify-between items-center border-b border-[#1F2937] pb-2">
                    <span className="text-xs font-bold text-red-400">RISK COMMAND RATING</span>
                    <span className="text-lg font-black text-red-500">{selectedDoc.risk} / 100</span>
                  </div>
                  <div className="space-y-1.5 text-[10px]">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Heuristic Impact Score:</span>
                      <span className="text-slate-300">{selectedDoc.risk}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Sentiment Score (Inference):</span>
                      <span className="text-slate-350">{selectedDoc.sentiment_score !== undefined ? parseFloat(selectedDoc.sentiment_score).toFixed(4) : "0.0000"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Reputation Impact Factor:</span>
                      <span className="text-[#D4AF37] font-bold">{selectedDoc.reputation_impact}</span>
                    </div>
                    <div className="flex justify-between border-t border-[#1F2937]/40 pt-1.5">
                      <span className="text-slate-500">Reputation Confidence Score:</span>
                      <span className="text-slate-300">{(selectedDoc.matchedExecObj?.confidence_score * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Evidence Coverage (Data Coverage):</span>
                      <span className="text-slate-300">{(selectedDoc.matchedExecObj?.data_coverage * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </div>

                {/* Original Article Content */}
                <div className="space-y-2">
                  <span className="text-[10px] text-slate-500 uppercase font-bold flex items-center">
                    <Info className="h-3.5 w-3.5 mr-1 text-[#D4AF37]" /> Original Article Snippet
                  </span>
                  <div className="bg-[#030712] border border-[#1F2937]/40 p-4 rounded text-[11px] text-slate-400 leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap">
                    {selectedDoc.original_content || "No original content available."}
                  </div>
                </div>

                {/* Related Narratives */}
                <div className="space-y-2">
                  <span className="text-[10px] text-slate-500 uppercase font-bold">Related Narrative Tracks</span>
                  <div className="flex flex-wrap gap-2">
                    {narratives && narratives.length > 0 ? (
                      narratives.slice(0, 2).map((n: any, idx: number) => (
                        <Badge key={idx} variant="outline" className="border-[#D4AF37]/30 text-[#D4AF37] text-[9px] bg-[#D4AF37]/5">
                          {n.theme_name || n.name}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-[10px] text-slate-500">No matching narrative tracks mapped.</span>
                    )}
                  </div>
                </div>

              </div>

              {/* Drawer Footer */}
              <div className="p-4 border-t border-[#1F2937]/80 bg-[#030712]/50 flex justify-end space-x-3">
                {selectedDocUrl && (
                  <a
                    href={selectedDocUrl}
                    target="_blank" 
                    rel="noopener noreferrer" 
                    className="flex items-center space-x-1.5 bg-[#D4AF37] hover:bg-[#bfa032] text-black font-bold font-mono text-[10px] rounded px-4 py-2"
                  >
                    <span>View Source Article</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                <button 
                  onClick={() => setSelectedDocId(null)} 
                  className="bg-transparent border border-[#1F2937] hover:border-slate-500 text-slate-400 hover:text-slate-200 text-[10px] rounded px-4 py-2"
                >
                  Close
                </button>
              </div>

            </div>
          </div>
        </div>
      )}

    </div>
  );
}
