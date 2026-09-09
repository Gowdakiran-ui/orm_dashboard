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
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, glassPill, glassPrimaryButton, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { ReputationScoreDefinition } from "@/lib/metricDefinitions";

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
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  // Shared theme-aware surface tokens -- same conventions RiskTab.tsx and
  // CompetitorsTab.tsx's search card already use, so this tab's dark-only
  // sections (previously hardcoded slate/#1F2937/#030712 colors that never
  // branched on isDark) now actually respond to the light/dark toggle.
  const cardBorder = isDark ? "border-white/[0.12]" : "border-black/[0.06]";
  const rowBorder = isDark ? "border-white/[0.08]" : "border-black/[0.06]";
  const rowHoverBg = isDark ? "hover:bg-white/[0.04]" : "hover:bg-black/[0.02]";
  const surfaceBg = isDark ? "bg-black/30" : "bg-black/[0.03]";
  const surfaceBorder = isDark ? "border-white/[0.08]" : "border-black/[0.06]";
  const inputClass = isDark
    ? "bg-zinc-950/60 border border-white/[0.12] text-zinc-100 placeholder:text-zinc-600 focus:border-[#38BDF8]/50"
    : "bg-white/70 border border-black/[0.08] text-zinc-900 placeholder:text-zinc-400 focus:border-[#3B82F6]/50";
  const drawerSurface = isDark ? "bg-zinc-950/95 border-white/[0.12]" : "bg-white/95 border-black/[0.06]";
  const chipClass = isDark ? "bg-[#030712] border border-white/[0.10] text-zinc-400" : "bg-black/[0.03] border border-black/[0.08] text-zinc-500";
  const tableHeaderBg = isDark ? "bg-black/20" : "bg-black/[0.02]";
  // 44x44px-floor touch target helper for compact icon/text action controls.
  const touchTarget = "min-h-[44px] inline-flex items-center justify-center";
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
      score: exec.score !== undefined && exec.score !== null ? exec.score.toFixed(2) : "N/A",
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
      <Card className={glassCard(theme)}>
        <CardHeader className={`pb-3 border-b ${cardBorder}`}>
          <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
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
              className={`flex-1 rounded px-3 py-2 text-xs font-mono focus:outline-none ${inputClass}`}
            />
            <button
              type="submit"
              disabled={searchLoading || !searchQuery.trim()}
              className={`bg-[#38BDF8] hover:bg-[#2ba8e0] disabled:opacity-50 disabled:cursor-not-allowed text-black font-bold font-mono text-xs rounded px-4 whitespace-nowrap ${touchTarget}`}
            >
              {searchLoading ? "Searching..." : "Search"}
            </button>
          </form>

          {searchErrorMsg && (
            <p className="text-red-500 font-mono text-xs">{searchErrorMsg}</p>
          )}

          {searchResult && searchResult.status === "searching" && (
            <div className={`border border-[#38BDF8]/30 rounded p-4 flex items-center space-x-3 ${surfaceBg}`}>
              <div className="h-3 w-3 rounded-full bg-[#38BDF8] animate-pulse" />
              <p className={`text-xs font-mono ${mutedText(theme)}`}>
                Running a fresh search — collecting and scoring coverage for {`"`}{searchQuery}{`"`}. This can take a while.
              </p>
            </div>
          )}

          {searchResult && searchResult.status === "tracked" && (
            <div className={`border border-[#D4AF37]/30 rounded p-4 space-y-2 ${surfaceBg}`}>
              <div className="flex items-center justify-between">
                <span className={`font-mono text-sm font-bold ${bodyText(theme)}`}>{searchResult.executive.name}</span>
                <Badge className="bg-[#D4AF37]/10 text-[#D4AF37] border border-[#D4AF37]/30 font-mono text-xs">TRACKED</Badge>
              </div>
              {searchResult.executive.health_status === 'INSUFFICIENT_EVIDENCE' ? (
                <p className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>
                  No qualifying coverage yet — tracked, but not enough evidence to score
                </p>
              ) : (
                <div className="grid grid-cols-3 gap-3 text-xs font-mono">
                  <div>
                    <span className={`block ${mutedText(theme)}`}>Score</span>
                    <span className="text-[#D4AF37] font-bold text-sm">
                      {searchResult.executive.score !== null ? searchResult.executive.score.toFixed(2) : 'N/A'}
                    </span>
                  </div>
                  <div>
                    <span className={`block ${mutedText(theme)}`}>Trend</span>
                    <span className={bodyText(theme)}>{searchResult.executive.trend ?? 'STABLE'}</span>
                  </div>
                  <div>
                    <span className={`block ${mutedText(theme)}`}>Grade</span>
                    <span className={bodyText(theme)}>{searchResult.executive.grade ?? 'N/A'}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {searchResult && searchResult.status === "unpromoted_candidate" && (
            <div className={`border border-amber-500/30 rounded p-4 space-y-2 ${surfaceBg}`}>
              <div className="flex items-center justify-between">
                <span className={`font-mono text-sm font-bold ${bodyText(theme)}`}>{searchResult.candidate.name}</span>
                <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/30 font-mono text-xs">NOT YET TRACKED</Badge>
              </div>
              <p className={`text-xs font-mono ${mutedText(theme)}`}>
                Discovered ({searchResult.candidate.mention_count} mentions, {(searchResult.candidate.confidence * 100).toFixed(0)}% confidence) but not yet promoted to a tracked executive — no reputation data exists for this name yet. Promote below to start tracking.
              </p>
            </div>
          )}

          {searchResult && searchResult.status === "invalid_name" && (
            <div className={`border rounded p-4 ${surfaceBorder} ${surfaceBg}`}>
              <p className={`text-xs font-mono uppercase tracking-wider text-center ${mutedText(theme)}`}>
                This doesn{`'`}t look like a valid person name{searchResult.reason ? ` — ${searchResult.reason}` : ""}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {!hasSelectedExecutive && (
        <Card className={`${glassCard(theme)} h-40`}>
          <CardContent className="h-full flex flex-col items-center justify-center space-y-2">
            <Users className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
            <p className={`font-mono text-xs ${mutedText(theme)}`}>No executive selected yet.</p>
            <p className={`font-mono text-xs ${mutedText(theme)}`}>Search a name above to start tracking a real executive.</p>
          </CardContent>
        </Card>
      )}

      {/* Executive Candidates Awaiting Promotion -- only shown when the
          current search resolves to unpromoted_candidate, not unconditional
          (hyperfocus redesign: no noise from historically-discovered names
          the user didn't just search for). */}
      {searchResult && searchResult.status === "unpromoted_candidate" && executiveCandidates.length > 0 && (
        <Card className={glassCard(theme)}>
          <CardHeader className={`pb-3 border-b ${cardBorder}`}>
            <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center justify-between`}>
              <span className="flex items-center">
                <AlertTriangle className="h-4 w-4 text-[#D4AF37] mr-2" />
                Promote {searchResult.candidate.name}
              </span>
            </CardTitle>
            <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>
              Found in already-collected coverage but not yet added as a tracked executive. Promoting applies the same confidence/mention checks to every pending name.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <button
              onClick={onPromoteExecutives}
              disabled={!onPromoteExecutives || promotingExecutives}
              className={`bg-[#D4AF37] hover:bg-[#bfa032] disabled:opacity-50 disabled:cursor-not-allowed text-black font-bold font-mono text-xs rounded px-4 ${touchTarget}`}
            >
              {promotingExecutives ? "Promoting..." : "Add This Executive"}
            </button>
          </CardContent>
        </Card>
      )}

      {hasSelectedExecutive && (
      <>
      {/* EXECUTIVE SUMMARY -- scoped to the one selected executive only. */}
      <Card className={`${glassCard(theme)} font-mono`}>
        <CardHeader className={`pb-3 border-b ${cardBorder}`}>
          <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
            <Trophy className="h-4 w-4 text-[#D4AF37] mr-2" />
            Executive Summary
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 grid gap-4 sm:grid-cols-3 text-xs">
          <div>
            <span className={`flex items-center gap-1 ${mutedText(theme)}`}>
              Reputation Score:
              <InfoTooltip label="About Reputation Score"><ReputationScoreDefinition /></InfoTooltip>
            </span>
            <span className={`font-bold ${bodyText(theme)}`}>{summary.score}</span>
          </div>
          <div>
            <span className={`block ${mutedText(theme)}`}>Latest Event:</span>
            <span className={`font-bold ${bodyText(theme)}`}>{summary.latestEvent}</span>
          </div>
          <div>
            <span className={`block ${mutedText(theme)}`}>Most Active Topic:</span>
            <span className={`font-bold ${bodyText(theme)}`}>{summary.activeTopic}</span>
          </div>
        </CardContent>
      </Card>

      {/* 2. Executive History Line Chart */}
      <ErrorBoundary fallback={<TelemetryErrorWidget title="Exec History Chart Error" />}>
        {execHistoryLoading ? (
          <Card className={`${glassTokens[theme].card} rounded-3xl h-[340px] animate-pulse`} />
        ) : (
          <Card className={glassCard(theme)}>
            <CardHeader>
              <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Reputation Trend</CardTitle>
              <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>Reputation score over time for this executive</CardDescription>
            </CardHeader>
            <CardContent className="pl-2">
              <div className="h-[280px]">
                {Object.keys(execHistory).length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <RechartsLineChart data={execTrendChartData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                      <XAxis dataKey="date" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                      <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} domain={[0, 100]} />
                      <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b' }} />
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
                      <div className={`border rounded p-4 flex flex-col items-center justify-center space-y-2 ${surfaceBorder} ${surfaceBg}`}>
                        <Users className={`h-6 w-6 mb-1 ${mutedText(theme)}`} />
                        <span className={`font-mono text-xs ${mutedText(theme)}`}>Executive In Focus</span>
                        <span className={`font-mono text-xl font-bold ${bodyText(theme)}`}>{singleExecutiveList.length}</span>
                      </div>
                      <div className={`border rounded p-4 flex flex-col items-center justify-center space-y-2 ${surfaceBorder} ${surfaceBg}`}>
                        <Activity className="h-6 w-6 text-[#D4AF37]/50 mb-1" />
                        <span className={`font-mono text-xs ${mutedText(theme)}`}>Data Status</span>
                        <Badge className="bg-[#D4AF37]/10 text-[#D4AF37] border border-[#D4AF37]/30 text-xs font-mono">Collecting</Badge>
                      </div>
                    </div>
                    <p className={`font-mono text-xs mt-4 uppercase ${mutedText(theme)}`}>Waiting for enough data points to plot a trend</p>
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
        <Card className={glassCard(theme)}>
          <CardHeader>
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
              <Activity className="h-4 w-4 text-emerald-500 mr-2" />
              Sentiment Breakdown
            </CardTitle>
            <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>How coverage of this executive splits by tone</CardDescription>
          </CardHeader>
          <CardContent className="h-[220px] pl-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sentimentData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                <XAxis dataKey="name" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b' }} />
                <Bar dataKey="value" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Executive Activity Timeline */}
        <Card className={glassCard(theme)}>
          <CardHeader>
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
              <Calendar className="h-4 w-4 text-[#38BDF8] mr-2" />
              Activity Timeline
            </CardTitle>
            <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>Coverage volume mentioning this executive, by day</CardDescription>
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
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                <XAxis dataKey="date" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b' }} />
                <Area type="monotone" dataKey="Mentions" stroke="#38BDF8" fillOpacity={1} fill="url(#colorMentions)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

      </div>

      {/* 4. EXECUTIVE SCORECARD */}
      <ErrorBoundary fallback={<TelemetryErrorWidget title="Executives Error" />}>
        {executivesLoading ? (
          <Card className={`${glassTokens[theme].card} rounded-3xl h-48 animate-pulse`} />
        ) : executivesError ? (
          <Card className={`${glassCard(theme)} border-red-500/20 h-48`}>
            <TelemetryErrorWidget title="Executives Telemetry Offline" message={executivesError} />
          </Card>
        ) : (
          <Card className={glassCard(theme)}>
            <CardHeader>
              <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
                <Users className="h-4 w-4 text-[#D4AF37] mr-2" />
                Executive Scorecard
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader className={`${rowBorder} ${tableHeaderBg}`}>
                  <TableRow className={rowBorder}>
                    <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>EXECUTIVE NAME</TableHead>
                    <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>REPUTATION SCORE</TableHead>
                    <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>CONFIDENCE</TableHead>
                    <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>EVIDENCE COVERAGE</TableHead>
                    <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>TREND</TableHead>
                    <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>TOP POSITIVE THEME</TableHead>
                    <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>TOP NEGATIVE THEME</TableHead>
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
                      <TableRow key={e.id ?? i} className={`${rowBorder} ${rowHoverBg} transition-colors`}>
                        <TableCell className={`font-mono text-xs font-bold ${bodyText(theme)}`}>{e.name}</TableCell>
                        <TableCell colSpan={6} className={`text-center font-mono text-xs uppercase tracking-wider py-3 ${mutedText(theme)}`}>
                          No qualifying coverage yet — tracked, but not enough evidence to score
                        </TableCell>
                      </TableRow>
                    ) : (
                      <TableRow key={e.id ?? i} className={`${rowBorder} ${rowHoverBg} transition-colors`}>
                        <TableCell className={`font-mono text-xs font-bold ${bodyText(theme)}`}>{e.name}</TableCell>
                        <TableCell className="text-center font-mono text-xs font-black text-[#D4AF37]">
                          {e.score !== undefined && e.score !== null ? e.score.toFixed(2) : 'N/A'}
                        </TableCell>
                        <TableCell className={`text-center font-mono text-xs ${bodyText(theme)}`}>
                          {e.confidence_score !== undefined ? `${(e.confidence_score * 100).toFixed(0)}%` : "100%"}
                          {e.health_status === 'PARTIAL' && (
                            <Badge className="ml-1.5 text-xs font-mono bg-amber-500/10 text-amber-500 border border-amber-500/30">
                              LIMITED DATA
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className={`text-center font-mono text-xs ${bodyText(theme)}`}>
                          {e.data_coverage !== undefined ? `${(e.data_coverage * 100).toFixed(0)}%` : "40%"}
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge className={`text-xs font-mono ${
                            e.trend === 'IMPROVING' ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/30" :
                            e.trend === 'DECLINING' ? "bg-red-500/10 text-red-500 border border-red-500/30" :
                            isDark ? "bg-zinc-500/10 text-zinc-300 border border-zinc-500/30" : "bg-zinc-500/10 text-zinc-600 border border-zinc-500/30"
                          }`}>
                            {e.trend ?? 'STABLE'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-emerald-500 font-mono text-xs truncate max-w-[120px]">{e.top_positive ?? 'None'}</TableCell>
                        <TableCell className="text-red-500 font-mono text-xs truncate max-w-[120px]">{e.top_negative ?? 'None'}</TableCell>
                      </TableRow>
                    )
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </ErrorBoundary>

      {/* 5. EXECUTIVE ACTIVITY TABLE */}
      <Card className={glassCard(theme)}>
        <CardHeader>
          <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center justify-between`}>
            <div className="flex items-center">
              <Search className="h-4 w-4 text-[#38BDF8] mr-2" />
              Executive Activity — {selectedExecutive?.name}
            </div>
            <Badge className="bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30 font-mono text-xs">
              {execEvents.length} Events
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader className={`${rowBorder} ${tableHeaderBg}`}>
              <TableRow className={rowBorder}>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>EXECUTIVE</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>EVENT HEADLINE</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>BUSINESS TOPIC</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>SENTIMENT</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>REPUTATION IMPACT</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>RISK SCORE</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>SOURCE</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>PUBLISHED DATE</TableHead>
                <TableHead className={`font-mono text-xs text-right ${mutedText(theme)}`}>ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {execEvents.map((doc, idx) => (
                <TableRow key={doc.id} className={`${rowBorder} ${rowHoverBg} transition-colors cursor-pointer`} onClick={() => setSelectedDocId(doc.id)}>
                  <TableCell className={`font-mono text-xs font-bold ${bodyText(theme)}`}>{doc.matchedExecutive}</TableCell>
                  <TableCell className={`font-mono text-xs max-w-[240px] truncate ${bodyText(theme)}`}>{doc.title}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className="border-[#D4AF37]/30 text-[#D4AF37] font-mono text-xs bg-[#D4AF37]/5">
                      {doc.topic}
                    </Badge>
                  </TableCell>
                  <TableCell className={`text-center font-mono text-xs ${bodyText(theme)}`}>
                    {doc.sentiment_score !== undefined ? parseFloat(doc.sentiment_score).toFixed(2) : "0.00"}
                  </TableCell>
                  <TableCell className={`text-center font-mono text-xs font-bold ${
                    parseFloat(doc.reputation_impact) >= 0 ? "text-emerald-500" : "text-red-500"
                  }`}>
                    {doc.reputation_impact}
                  </TableCell>
                  <TableCell className={`text-center font-mono text-xs font-bold ${
                    doc.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-500" : doc.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-orange-500" : "text-yellow-600"
                  }`}>
                    {Math.round(doc.risk || 0)}
                  </TableCell>
                  <TableCell className={`font-mono text-xs truncate max-w-[100px] ${mutedText(theme)}`}>{doc.source}</TableCell>
                  <TableCell className={`font-mono text-xs ${mutedText(theme)}`}>
                    {doc.timestamp ? new Date(doc.timestamp).toLocaleDateString(undefined, { dateStyle: 'short' }) : "N/A"}
                  </TableCell>
                  <TableCell className="text-right">
                    <button
                      onClick={(e) => { e.stopPropagation(); setSelectedDocId(doc.id); }}
                      className={`bg-blue-600 hover:bg-blue-700 cursor-pointer text-white font-mono text-xs rounded px-3 ${touchTarget}`}
                    >
                      Details
                    </button>
                  </TableCell>
                </TableRow>
              ))}
              {execEvents.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className={`text-center py-10 font-mono text-xs ${mutedText(theme)}`}>
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

      {/* Slide-Over Details Drawer -- kept high-opacity (not the standard
          glass alpha) for the same legibility reason as RiskTab.tsx's
          drawers: at full page height over a dimmed backdrop, translucency
          reads poorly on long paragraph text. */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 overflow-hidden font-mono">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setSelectedDocId(null)} />
          <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
            <div className={`w-[600px] backdrop-blur-2xl border-l flex flex-col justify-between shadow-2xl animate-in slide-in-from-right duration-300 ${bodyText(theme)} ${drawerSurface}`}>

              {/* Header */}
              <div className={`p-6 border-b flex items-center justify-between ${cardBorder}`}>
                <div className="flex items-center space-x-3">
                  <AlertOctagon className="h-5 w-5 text-red-500" />
                  <span className="text-sm font-bold uppercase text-[#D4AF37]">Details</span>
                </div>
                <button
                  onClick={() => setSelectedDocId(null)}
                  className={`flex items-center gap-1.5 text-xs transition-colors ${mutedText(theme)} ${isDark ? "hover:text-zinc-100" : "hover:text-zinc-900"} ${touchTarget}`}
                >
                  <X className="h-5 w-5" />
                  <span>Close</span>
                </button>
              </div>

              {/* Content Panel */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">

                {/* Headline & Meta */}
                <div className="space-y-2">
                  <h3 className={`text-sm font-bold leading-snug ${bodyText(theme)}`}>{selectedDoc.title}</h3>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Source: {selectedDoc.source}</span>
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Topic: {selectedDoc.topic}</span>
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Executive: {selectedDoc.matchedExecutive}</span>
                  </div>
                </div>

                {/* Risk & Sentiment score calculations */}
                <div className={`p-4 rounded border border-red-500/20 space-y-3 ${surfaceBg}`}>
                  <div className={`flex justify-between items-center border-b pb-2 ${cardBorder}`}>
                    <span className="text-xs font-bold text-red-500">Risk Rating</span>
                    <span className="text-lg font-black text-red-500">{selectedDoc.risk} / 100</span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Impact Score:</span>
                      <span className={bodyText(theme)}>{selectedDoc.risk}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Sentiment Score:</span>
                      <span className={bodyText(theme)}>{selectedDoc.sentiment_score !== undefined ? parseFloat(selectedDoc.sentiment_score).toFixed(2) : "0.00"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Reputation Impact:</span>
                      <span className="text-[#D4AF37] font-bold">{selectedDoc.reputation_impact}</span>
                    </div>
                    <div className={`flex justify-between border-t pt-1.5 ${surfaceBorder}`}>
                      <span className={mutedText(theme)}>Confidence:</span>
                      <span className={bodyText(theme)}>{(selectedDoc.matchedExecObj?.confidence_score * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Evidence Coverage:</span>
                      <span className={bodyText(theme)}>{(selectedDoc.matchedExecObj?.data_coverage * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </div>

                {/* Original Article Content */}
                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold flex items-center ${mutedText(theme)}`}>
                    <Info className="h-3.5 w-3.5 mr-1 text-[#D4AF37]" /> Original Article Snippet
                  </span>
                  <div className={`border p-4 rounded text-xs leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap ${mutedText(theme)} ${surfaceBorder} ${surfaceBg}`}>
                    {selectedDoc.original_content || "No original content available."}
                  </div>
                </div>

                {/* Related Narratives */}
                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold ${mutedText(theme)}`}>Related Narratives</span>
                  <div className="flex flex-wrap gap-2">
                    {narratives && narratives.length > 0 ? (
                      narratives.slice(0, 2).map((n: any, idx: number) => (
                        <Badge key={idx} variant="outline" className="border-[#D4AF37]/30 text-[#D4AF37] text-xs bg-[#D4AF37]/5">
                          {n.theme_name || n.name}
                        </Badge>
                      ))
                    ) : (
                      <span className={`text-xs ${mutedText(theme)}`}>No matching narratives mapped.</span>
                    )}
                  </div>
                </div>

              </div>

              {/* Drawer Footer */}
              <div className={`p-4 border-t flex justify-end space-x-3 ${cardBorder} ${isDark ? "bg-black/20" : "bg-black/[0.02]"}`}>
                {selectedDocUrl && (
                  <a
                    href={selectedDocUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`flex items-center space-x-1.5 bg-[#D4AF37] hover:bg-[#bfa032] text-black font-bold font-mono text-xs rounded px-4 ${touchTarget}`}
                  >
                    <span>View Source Article</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                <button
                  onClick={() => setSelectedDocId(null)}
                  className={`bg-transparent border text-xs rounded px-4 transition-colors ${mutedText(theme)} ${isDark ? "border-white/[0.12] hover:border-zinc-500 hover:text-zinc-100" : "border-black/[0.08] hover:border-zinc-400 hover:text-zinc-900"} ${touchTarget}`}
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
