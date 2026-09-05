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
  TrendingUp, Calendar, AlertOctagon, X, ExternalLink
} from "lucide-react";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";
import { fetchDocumentDetails, searchExecutive } from "@/lib/api";

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
  executiveCandidates?: any[];
  onPromoteExecutives?: () => void;
  promotingExecutives?: boolean;
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
  clientId,
  executiveCandidates = [],
  onPromoteExecutives,
  promotingExecutives = false
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

  // Executive search: hyperfocus redesign, same pattern as CompetitorsTab's
  // search-first CompetitorsTab.tsx. Four backend states (tracked /
  // unpromoted_candidate / searching / invalid_name), plus a fifth
  // transient one the frontend drives by polling: a "searching" response
  // means a fresh brand-scoped search was just triggered (or is still in
  // flight) -- real async collection, not instant. Same never-conflate-
  // states principle as CompetitorsTab: "searching"/"unpromoted_candidate"/
  // "invalid_name" are never rendered as if they were verified reputation
  // data.
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState<any | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchErrorMsg, setSearchErrorMsg] = useState<string | null>(null);
  const searchPollRef = React.useRef<{ cancelled: boolean }>({ cancelled: false });

  // Same realistic patience window as CompetitorsTab's competitor-search --
  // a genuinely-new name's fresh collection goes through the same
  // ~9-10s/doc NLP bottleneck, so a short timeout would prematurely report
  // "taking longer than expected" on a search that's actually still working.
  const MAX_SEARCH_POLLS = 450; // ~45 minutes at 6s intervals
  const SEARCH_POLL_INTERVAL_MS = 6000;

  async function pollExecutiveSearch(query: string, attempt: number) {
    if (searchPollRef.current.cancelled || !clientId) return;
    try {
      const result = await searchExecutive(clientId, query);
      if (searchPollRef.current.cancelled) return;
      setSearchResult(result);
      if (result?.status === "searching") {
        if (attempt >= MAX_SEARCH_POLLS) {
          setSearchErrorMsg("Search is taking longer than expected — try again in a few minutes.");
          setSearchLoading(false);
          return;
        }
        setTimeout(() => pollExecutiveSearch(query, attempt + 1), SEARCH_POLL_INTERVAL_MS);
      } else {
        setSearchLoading(false);
      }
    } catch (err: any) {
      if (searchPollRef.current.cancelled) return;
      setSearchErrorMsg(err?.message || "Search failed");
      setSearchResult(null);
      setSearchLoading(false);
    }
  }

  async function handleExecutiveSearch(e: React.FormEvent) {
    e.preventDefault();
    const query = searchQuery.trim();
    if (!clientId || !query) return;
    searchPollRef.current.cancelled = false;
    setSearchLoading(true);
    setSearchErrorMsg(null);
    setSearchResult(null);
    pollExecutiveSearch(query, 1);
  }

  useEffect(() => {
    return () => { searchPollRef.current.cancelled = true; };
  }, []);

  // Hyperfocus redesign (same principle as CompetitorsTab.tsx): this tab
  // shows exactly one executive at a time -- whichever one is currently
  // searched -- never every historically-tracked executive a client happens
  // to have accumulated. `selectedExecutive` is the single source of truth
  // for "what executive is in focus"; it's null (blank page) until a search
  // resolves to a real tracked executive, and goes null again the instant a
  // new search starts (handleExecutiveSearch's setSearchResult(null)).
  const selectedExecutive = searchResult && searchResult.status === "tracked" ? searchResult.executive : null;
  const hasSelectedExecutive = !!selectedExecutive;

  // Same row shape the (now-unused-by-default) `executives` prop provided,
  // but containing only the one executive in focus -- lets the existing
  // per-row computations below (summary/distribution/sentiment/timeline/
  // influence) work unchanged on a single-item list instead of a fleet.
  const singleExecutiveList = useMemo(() => {
    if (!selectedExecutive) return [];
    return [{
      id: selectedExecutive.entity_id,
      name: selectedExecutive.name,
      score: selectedExecutive.score,
      grade: selectedExecutive.grade,
      trend: selectedExecutive.trend,
      top_positive: selectedExecutive.top_positive,
      top_negative: selectedExecutive.top_negative,
      confidence_score: selectedExecutive.confidence_score,
      data_coverage: selectedExecutive.data_coverage,
      health_status: selectedExecutive.health_status,
    }];
  }, [selectedExecutive]);

  // 1. EXECUTIVE NAMES CACHE
  const execNames = useMemo(() => {
    return (singleExecutiveList || []).map(e => e.name.toLowerCase());
  }, [singleExecutiveList]);

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
        const matchedExec = (singleExecutiveList || []).find(e =>
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
  }, [documents, execNames, singleExecutiveList]);

  const selectedDoc = useMemo(() => {
    if (!selectedDocId) return null;
    return execEvents.find(d => d.id === selectedDocId) || null;
  }, [selectedDocId, execEvents]);

  // 3. EXECUTIVE INTEL SUMMARY METRICS -- simplified for the hyperfocus
  // redesign. With exactly one executive in focus, "highest reputation" /
  // "highest risk" / "most mentioned" would always just echo the one
  // selected executive's own name back, which is noise, not information
  // (same reasoning CompetitorsTab.tsx's summary card simplification used).
  const summary = useMemo(() => {
    const exec = singleExecutiveList[0];
    if (!exec) {
      return {
        score: "N/A",
        latestEvent: "Insufficient historical data",
        activeTopic: "Insufficient historical data"
      };
    }
    const latestEvent = execEvents[0]?.timestamp
      ? new Date(execEvents[0].timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
      : "Insufficient historical data";
    const topicCounts = execEvents.map(d => d.topic).filter(Boolean).reduce((acc, t) => {
      acc[t] = (acc[t] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);
    const activeTopic = Object.entries(topicCounts).sort((a, b) => (b[1] as number) - (a[1] as number))[0]?.[0] || "General";
    return {
      score: exec.score !== undefined && exec.score !== null ? exec.score.toFixed(1) : "N/A",
      latestEvent,
      activeTopic
    };
  }, [singleExecutiveList, execEvents]);

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

  return (
    <div className="space-y-6">

      {/* EXECUTIVE SEARCH -- the only path onto this tab's data now. No
          candidate lists, no scorecard, no auto-surfaced noise: a name
          either matches a real tracked executive, a discovered-but-
          unpromoted candidate, is rejected as not shaped like a real
          person's name, or triggers a scoped fresh search. */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
        <CardHeader className="pb-3 border-b border-[#1F2937]/40">
          <CardTitle className="text-xs uppercase tracking-wider text-slate-400 flex items-center">
            <Search className="h-4 w-4 text-[#38BDF8] mr-2" />
            Search Executives
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 space-y-4">
          <form onSubmit={handleExecutiveSearch} className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search executive name..."
              className="flex-1 bg-[#030712] border border-[#1F2937]/60 rounded px-3 py-2 text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-[#38BDF8]/50"
            />
            <button
              type="submit"
              disabled={searchLoading || !searchQuery.trim()}
              className="bg-[#38BDF8] hover:bg-[#2ba8e0] disabled:opacity-50 disabled:cursor-not-allowed text-black font-bold font-mono text-[10px] rounded px-4 py-2 whitespace-nowrap"
            >
              {searchLoading ? "Searching..." : "Search"}
            </button>
          </form>

          {searchErrorMsg && (
            <p className="text-red-400 font-mono text-[10px]">{searchErrorMsg}</p>
          )}

          {searchResult && searchResult.status === "searching" && (
            <div className="border border-[#38BDF8]/30 bg-[#030712] rounded p-4 flex items-center space-x-3">
              <div className="h-3 w-3 rounded-full bg-[#38BDF8] animate-pulse" />
              <p className="text-[10px] font-mono text-slate-400">
                Running a fresh, brand-scoped search — collecting and scoring coverage for this name alongside {`"`}{searchQuery}{`"`}. This can take a while.
              </p>
            </div>
          )}

          {searchResult && searchResult.status === "tracked" && (
            <div className="border border-[#D4AF37]/30 bg-[#030712] rounded p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-bold text-slate-200">{searchResult.executive.name}</span>
                <Badge className="bg-[#D4AF37]/10 text-[#D4AF37] border border-[#D4AF37]/30 font-mono text-[9px]">TRACKED</Badge>
              </div>
              {searchResult.executive.health_status === 'INSUFFICIENT_EVIDENCE' ? (
                <p className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                  No qualifying coverage yet — tracked, but not enough evidence to score
                </p>
              ) : (
                <div className="grid grid-cols-3 gap-3 text-[10px] font-mono">
                  <div>
                    <span className="text-slate-500 block">Score</span>
                    <span className="text-[#D4AF37] font-bold text-sm">
                      {searchResult.executive.score !== null ? searchResult.executive.score.toFixed(1) : 'N/A'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Trend</span>
                    <span className="text-slate-200">{searchResult.executive.trend ?? 'STABLE'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Grade</span>
                    <span className="text-slate-200">{searchResult.executive.grade ?? 'N/A'}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {searchResult && searchResult.status === "unpromoted_candidate" && (
            <div className="border border-amber-500/30 bg-[#030712] rounded p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-bold text-slate-200">{searchResult.candidate.name}</span>
                <Badge className="bg-amber-500/10 text-amber-400 border border-amber-500/30 font-mono text-[9px]">NOT YET TRACKED</Badge>
              </div>
              <p className="text-[10px] font-mono text-slate-500">
                Discovered ({searchResult.candidate.mention_count} mentions, {(searchResult.candidate.confidence * 100).toFixed(0)}% confidence) but not yet promoted to a tracked executive — no reputation data exists for this name yet. Promote below to start tracking.
              </p>
            </div>
          )}

          {searchResult && searchResult.status === "invalid_name" && (
            <div className="border border-[#1F2937]/60 bg-[#030712] rounded p-4">
              <p className="text-[10px] font-mono text-slate-500 uppercase tracking-wider text-center">
                This doesn{`'`}t look like a valid person name{searchResult.reason ? ` — ${searchResult.reason}` : ""}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {!hasSelectedExecutive && (
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 h-40">
          <CardContent className="h-full flex flex-col items-center justify-center space-y-2">
            <Users className="h-6 w-6 text-slate-500 opacity-60" />
            <p className="text-slate-500 font-mono text-xs">No executive selected yet.</p>
            <p className="text-slate-600 font-mono text-[9px]">Search a name above to start tracking a real executive.</p>
          </CardContent>
        </Card>
      )}

      {/* Executive Candidates Awaiting Promotion -- only shown when the
          current search resolves to unpromoted_candidate, not unconditional
          (hyperfocus redesign: no noise from historically-discovered names
          the user didn't just search for). */}
      {searchResult && searchResult.status === "unpromoted_candidate" && executiveCandidates.length > 0 && (
        <Card className="bg-[#060B18]/60 border-[#D4AF37]/30 shadow-2xl">
          <CardHeader className="pb-3 border-b border-[#1F2937]/40">
            <CardTitle className="text-xs uppercase tracking-wider text-slate-400 flex items-center justify-between">
              <span className="flex items-center">
                <AlertTriangle className="h-4 w-4 text-[#D4AF37] mr-2" />
                Promote {searchResult.candidate.name}
              </span>
            </CardTitle>
            <CardDescription className="text-[10px] font-mono text-slate-500">
              Discovered via NER on ingested documents but not yet promoted to a tracked executive. Promotion applies confidence/mention thresholds automatically across all pending candidates.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <button
              onClick={onPromoteExecutives}
              disabled={!onPromoteExecutives || promotingExecutives}
              className="bg-[#D4AF37] hover:bg-[#bfa032] disabled:opacity-50 disabled:cursor-not-allowed text-black font-bold font-mono text-[10px] rounded px-4 py-2"
            >
              {promotingExecutives ? "Promoting..." : "Run Promotion Check"}
            </button>
          </CardContent>
        </Card>
      )}

      {hasSelectedExecutive && (
      <>
      {/* EXECUTIVE INTELLIGENCE SUMMARY -- scoped to the one selected
          executive only. */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl font-mono">
        <CardHeader className="pb-3 border-b border-[#1F2937]/40">
          <CardTitle className="text-xs uppercase tracking-wider text-slate-400 flex items-center">
            <Trophy className="h-4 w-4 text-[#D4AF37] mr-2" />
            Executive Intelligence Summary
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 grid gap-4 sm:grid-cols-3 text-[10px]">
          <div>
            <span className="text-slate-500 block">Reputation Score:</span>
            <span className="text-slate-200 font-bold">{summary.score}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Latest Event:</span>
            <span className="text-slate-200 font-bold">{summary.latestEvent}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Most Active Topic:</span>
            <span className="text-slate-200 font-bold">{summary.activeTopic}</span>
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
                        <span className="font-mono text-xs text-slate-400">Executive In Focus</span>
                        <span className="font-mono text-xl font-bold text-slate-200">{singleExecutiveList.length}</span>
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

      {/* 3. DUAL VISUALIZATIONS -- Reputation Distribution and Influence
          Ranking removed per hyperfocus redesign: both were rankings/
          histograms across every historically-tracked executive, which are
          meaningless with exactly one executive in focus. */}
      <div className="grid gap-6 md:grid-cols-2">

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
                  {singleExecutiveList.map((e, i) => (
                    e.health_status === 'INSUFFICIENT_EVIDENCE' ? (
                      // Honest empty state: a real 0.0/NA computed for zero-evidence
                      // executives (executive_reputation_engine.py's own zero-evidence
                      // sentinel) previously rendered as a plain "0.0" score -- visually
                      // identical to a genuinely bad reputation. Surface the real reason
                      // instead of a number that looks broken.
                      <TableRow key={e.id ?? i} className="border-[#1F2937]/40 hover:bg-[#060B18] transition-colors">
                        <TableCell className="font-mono text-xs font-bold text-slate-200">{e.name}</TableCell>
                        <TableCell colSpan={6} className="text-center font-mono text-[10px] text-slate-500 uppercase tracking-wider py-3">
                          No qualifying coverage yet — tracked, but not enough evidence to score
                        </TableCell>
                      </TableRow>
                    ) : (
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
                    )
                  ))}
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
              EXECUTIVE INTELLIGENCE REGISTER — {selectedExecutive?.name}
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
      </>
      )}

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
