import React, { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { 
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer 
} from 'recharts';
import { 
  Compass, Users, BarChart3, Search, ShieldCheck,
  Trophy, Info, Activity, Calendar, AlertOctagon, X, ExternalLink
} from "lucide-react";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";
import { calculateClientSOV } from "@/utils/shareOfVoice";
import { fetchDocumentDetails, searchCompetitor } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, glassPill, glassPrimaryButton, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";

export interface CompetitorsTabProps {
  benchmarksLoading: boolean;
  benchmarksError: string | null;
  benchmarks: any[];
  competitorRadarData: any[];
  activeClientName: string;
  normalizedBenchmarks: any[];
  reputation: any;
  repBreakdown: any;
  clientRank: string;
  documents: any[]; // Pipe documents list for dynamic register calculations
  clientId?: string | null;
}

export function CompetitorsTab({
  benchmarksLoading,
  benchmarksError,
  benchmarks,
  competitorRadarData,
  activeClientName,
  normalizedBenchmarks,
  reputation,
  repBreakdown,
  clientRank,
  documents,
  clientId,
}: CompetitorsTabProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  // Shared theme-aware surface tokens for the sections below that were
  // previously hardcoded to a fixed dark palette (text-slate-*,
  // border-[#1F2937], bg-[#030712]/[#060B18]) and never branched on isDark
  // -- same conventions the search card above (and RiskTab.tsx) already use.
  const cardBorder = isDark ? "border-white/[0.12]" : "border-black/[0.06]";
  const rowBorder = isDark ? "border-white/[0.08]" : "border-black/[0.06]";
  const rowHoverBg = isDark ? "hover:bg-white/[0.04]" : "hover:bg-black/[0.02]";
  const surfaceBg = isDark ? "bg-black/30" : "bg-black/[0.03]";
  const surfaceBorder = isDark ? "border-white/[0.08]" : "border-black/[0.06]";
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

  // Competitor search (TASK.md Part 2.2-2.5): search-first, zero-noise --
  // three backend states (tracked / unpromoted_candidate / searching) plus a
  // fourth transient one the frontend drives by polling: a "searching"
  // response means a fresh search was just triggered (or is still in
  // flight) and collection/processing is real async work, not instant.
  // Same never-conflate-states principle as ExecutivesTab's search: a
  // "searching" or "unpromoted_candidate" result is never rendered as if it
  // were verified comparison data.
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState<any | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchErrorMsg, setSearchErrorMsg] = useState<string | null>(null);
  const searchPollRef = React.useRef<{ cancelled: boolean }>({ cancelled: false });

  // A genuinely-new competitor name's fresh-search collects real documents
  // (Google News alone routinely returns 50-100+ for an actively-covered
  // topic) and each one goes through the same ~9-10s/doc zero-shot topic
  // classification bottleneck already measured elsewhere in this pipeline
  // (see the Run Pipeline timing investigation) -- there is no fast path.
  // Live-measured case: searching "DeepSeek" for the Anthropic client
  // collected 163 real documents across the 3 feeds; even with the NLP
  // queue otherwise idle, only ~35 had finished after 8 minutes (~14s/doc),
  // projecting to roughly 35-40 minutes for the full backlog. The previous
  // 2-minute window (20 polls x 6s) wasn't a bug in the search itself --
  // search_client_competitor kept correctly returning {status: "searching"}
  // the whole time, never stuck, never erroring -- it just gave up on an
  // honest "still working" answer far too early for realistic volumes.
  const MAX_SEARCH_POLLS = 450; // ~45 minutes at 6s intervals
  const SEARCH_POLL_INTERVAL_MS = 6000;

  async function pollCompetitorSearch(query: string, attempt: number) {
    if (searchPollRef.current.cancelled || !clientId) return;
    try {
      const result = await searchCompetitor(clientId, query);
      if (searchPollRef.current.cancelled) return;
      setSearchResult(result);
      if (result?.status === "searching") {
        if (attempt >= MAX_SEARCH_POLLS) {
          setSearchErrorMsg("Search is taking longer than expected — try again in a few minutes.");
          setSearchLoading(false);
          return;
        }
        setTimeout(() => pollCompetitorSearch(query, attempt + 1), SEARCH_POLL_INTERVAL_MS);
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

  async function handleCompetitorSearch(e: React.FormEvent) {
    e.preventDefault();
    const query = searchQuery.trim();
    if (!clientId || !query) return;
    searchPollRef.current.cancelled = false;
    setSearchLoading(true);
    setSearchErrorMsg(null);
    setSearchResult(null);
    pollCompetitorSearch(query, 1);
  }

  useEffect(() => {
    return () => { searchPollRef.current.cancelled = true; };
  }, []);

  // Hyperfocus redesign (per explicit product direction): this tab shows
  // exactly one competitor at a time -- whichever one is currently searched
  // -- never every historically-tracked competitor a client happens to have
  // accumulated. `selectedCompetitor` is the single source of truth for
  // "what competitor is in focus"; it's null (blank page) until a search
  // resolves to a real tracked competitor, and goes null again the instant a
  // new search starts (handleCompetitorSearch's setSearchResult(null)), so
  // switching searches never briefly shows the old competitor's data next
  // to the new query.
  const selectedCompetitor = searchResult && searchResult.status === "tracked" ? searchResult.competitor : null;

  // Same row shape normalizedBenchmarks (the old all-competitors prop) used,
  // but containing only the one competitor in focus -- lets the rest of
  // this component's existing per-row logic (rank/evidence/threat display)
  // work unchanged on a single-item list instead of a fleet.
  const singleCompetitorBenchmarks = useMemo(() => {
    if (!selectedCompetitor) return [];
    return [{
      competitor_id: selectedCompetitor.entity_id,
      competitor_name: selectedCompetitor.name,
      rank: selectedCompetitor.rank ?? 0,
      sov: selectedCompetitor.share_of_voice ?? 0,
      reputation: selectedCompetitor.reputation_score ?? 0,
      sentiment: selectedCompetitor.sentiment_score ?? 0,
      risk: selectedCompetitor.risk_score ?? 0,
    }];
  }, [selectedCompetitor]);

  // Radar data built locally from just [client, selectedCompetitor] --
  // deliberately not the parent's `competitorRadarData` prop, which is
  // computed in useAnalytics.ts across every historically-tracked
  // competitor. Same subject/axis shape and normalization the old multi-
  // competitor radar used (sentiment (x+1)*50, risk containment = 100-risk),
  // just fed by one competitor instead of all of them.
  const singleCompetitorRadarData = useMemo(() => {
    const clientAvgRisk = repBreakdown?.risk !== undefined && repBreakdown?.risk !== null ? repBreakdown.risk : 0;
    const data: any[] = [
      { subject: "Reputation Score" },
      { subject: "Sentiment Score" },
      { subject: "Risk Containment" },
      { subject: "Share of Voice" }
    ];
    data[0][activeClientName] = reputation?.score ?? 0;
    data[1][activeClientName] = repBreakdown?.sentiment ?? 0;
    data[2][activeClientName] = 100 - clientAvgRisk;
    data[3][activeClientName] = calculateClientSOV(singleCompetitorBenchmarks);

    if (selectedCompetitor) {
      data[0][selectedCompetitor.name] = selectedCompetitor.reputation_score ?? 0;
      data[1][selectedCompetitor.name] = ((selectedCompetitor.sentiment_score ?? 0) + 1) * 50;
      data[2][selectedCompetitor.name] = 100 - (selectedCompetitor.risk_score ?? 0);
      data[3][selectedCompetitor.name] = selectedCompetitor.share_of_voice ?? 0;
    }
    return data;
  }, [activeClientName, reputation, repBreakdown, selectedCompetitor, singleCompetitorBenchmarks]);

  // 1. CLIENT + THE ONE SELECTED COMPETITOR
  // C3: rank is no longer computed here. There were three independent,
  // disagreeing rank computations in this codebase: the backend `rank`
  // column (BenchmarkEngine, per A2.12/B6 — the canonical one, comparable
  // across client+competitors on one formula), useAnalytics.ts's
  // `clientRankValue`/`clientRank`, and this component's own tie-aware
  // recomputation. Per A9/B6, the backend field is authoritative for
  // competitors; the client's brand entity has no benchmark row of its own
  // to read a backend rank from, so `clientRank` (computed in useAnalytics.ts
  // from the same reputation comparison the backend ranking uses) is the one
  // client-side stand-in, now actually wired in below instead of being a
  // dead prop. This memo only builds row data for display/sorting; it does
  // not invent a rank number.
  const rankedBrands = useMemo(() => {
    const clientRep = reputation?.score ?? 0;
    const clientSent = repBreakdown?.sentiment ?? 0;
    const clientRisk = repBreakdown?.risk !== undefined && repBreakdown?.risk !== null
      ? 100 - repBreakdown.risk
      : 0;

    // Calculate Client SOV
    const clientSOV = calculateClientSOV(singleCompetitorBenchmarks);

    const list = [
      {
        name: activeClientName,
        isClient: true,
        reputation: clientRep,
        sentiment: clientSent,
        hasEvidence: true,
        risk: clientRisk,
        sov: clientSOV,
        rankStr: clientRank
      },
      ...(singleCompetitorBenchmarks || []).map(b => ({
        name: b.competitor_name,
        isClient: false,
        reputation: b.reputation ?? 0,
        // C1: client sentiment (repBreakdown.sentiment) is already 0-100
        // (ReputationEngine's ((avg+1)/2)*100). Competitor sentiment from
        // /benchmark is the raw -1..+1 average — normalize with the same
        // (x+1)*50 mapping the radar chart already uses below, so both are
        // on the same scale before they're compared in this table/summary.
        sentiment: ((b.sentiment ?? 0) + 1) * 50,
        // C5: `b.rank` is already the canonical zero-evidence signal (0 =
        // unranked, per B6/C3/A2.10 below) — confirmed live that
        // rank/health_status/confidence_score always agree (0 disagreements
        // across every current benchmark row), so this reuses that same
        // signal instead of introducing a second, possibly-inconsistent
        // check. A zero-evidence competitor's `sentiment` is still the raw
        // (0+1)*50=50 computed above (not touched — same value used for
        // sorting/leader calcs as before this fix), but the table cell
        // below renders "No Data" instead of that number for it, so a
        // fabricated neutral score is never shown as if it were real.
        hasEvidence: !!b.rank,
        risk: b.risk ?? 0,
        sov: b.sov ?? 0,
        // B6/C3: backend rank, 0 = unranked (no evidence — A2.10).
        rankStr: b.rank ? `#${b.rank}` : "Unranked"
      }))
    ];

    // Sort primarily by Reputation Score (descending), secondary by name to ensure absolute determinism
    list.sort((a, b) => {
      if (Math.abs(b.reputation - a.reputation) > 0.0001) {
        return b.reputation - a.reputation;
      }
      return a.name.localeCompare(b.name);
    });

    return list;
  }, [activeClientName, reputation, repBreakdown, singleCompetitorBenchmarks, clientRank]);

  // 2. CLIENT VS. SELECTED COMPETITOR SUMMARY
  // Simplified for the hyperfocus redesign: with exactly one competitor in
  // view, "closest threat" / "highest SOV" / "highest risk competitor" would
  // always just be that same one name repeated back three times -- noise,
  // not information. Keep only what's actually different with two entities:
  // who's ahead on reputation, and a recommendation naming the competitor.
  const summary = useMemo(() => {
    if (singleCompetitorBenchmarks.length === 0) return null;

    const leader = [...rankedBrands].sort((a, b) => b.reputation - a.reputation)[0];
    const clientBrand = rankedBrands.find(b => b.isClient);
    const competitor = rankedBrands.find(b => !b.isClient);

    let recommendation = "Maintain market visibility and monitor key brand metrics.";
    if (clientBrand && leader && leader.isClient) {
      recommendation = `Maintain market leadership by prioritizing high-sentiment narrative tracks. Monitor ${competitor ? competitor.name : "this competitor"} closely.`;
    } else if (clientBrand && leader && !leader.isClient) {
      recommendation = `Increase visibility and address sentiment deficits to close the gap with ${leader.name}.`;
    }
    if (competitor && competitor.risk > 40) {
      recommendation += ` Watch ${competitor.name} for volatile risk escalations.`;
    }

    return {
      leader: leader?.name || "N/A",
      recommendation
    };
  }, [rankedBrands, singleCompetitorBenchmarks]);

  // 4. VERIFIED COMPETITOR EVENTS FILTERING -- scoped to the one selected
  // competitor only (hyperfocus redesign). Previously this matched against
  // every historically-tracked competitor; the register below must now only
  // ever contain events for whichever single competitor is in focus.
  const competitorNames = useMemo(() => {
    return (singleCompetitorBenchmarks || []).map(b => b.competitor_name.toLowerCase());
  }, [singleCompetitorBenchmarks]);

  const competitorEvents = useMemo(() => {
    // C5: attribution now comes only from `extracted_entities`, which is the
    // API's projection of actual entity_mentions rows (documents.py joins
    // EntityMention -> Entity) — a real, verified link between this document
    // and a specific entity. The previous version also matched on a naive
    // case-insensitive substring search over title+content with no word
    // boundary, so any Apple article mentioning "NASDAQ" or "Guardian" in
    // passing text got attributed to those as if they were the subject.
    return (documents || [])
      .map(d => {
        if (!d) return null;
        const mention = (d.extracted_entities || []).find((e: any) =>
          e && e.name && competitorNames.includes(e.name.toLowerCase())
        );
        if (!mention) return null;
        const matchedComp = (singleCompetitorBenchmarks || []).find(b =>
          b.competitor_name.toLowerCase() === mention.name.toLowerCase()
        );
        return {
          ...d,
          matchedCompetitor: matchedComp ? matchedComp.competitor_name : mention.name
        };
      })
      .filter((d): d is NonNullable<typeof d> => d !== null)
      .sort((a, b) => {
        const dateA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
        const dateB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
        return dateB - dateA;
      });
  }, [documents, competitorNames, singleCompetitorBenchmarks]);

  const selectedDoc = useMemo(() => {
    if (!selectedDocId) return null;
    return competitorEvents.find(d => d.id === selectedDocId) || null;
  }, [selectedDocId, competitorEvents]);

  // 5. ACTIVITY SUMMARY STATS -- scoped to the one selected competitor.
  // "Highest impact competitor" / "most mentioned competitor" fields were
  // dropped: with exactly one competitor in focus, both would always just
  // echo its own name back, which is noise, not information.
  const activitySummary = useMemo(() => {
    const total = competitorEvents.length;
    if (total === 0) {
      return {
        total: 0,
        latestEvent: "Insufficient historical data",
        activeTopic: "Insufficient historical data"
      };
    }

    // Latest competitor event timestamp
    const latestEvent = competitorEvents[0]?.timestamp
      ? new Date(competitorEvents[0].timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
      : "N/A";

    // Most active topic
    const topicCounts = competitorEvents.map(d => d.topic).filter(Boolean).reduce((acc, t) => {
      acc[t] = (acc[t] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);
    const activeTopic = Object.entries(topicCounts).sort((a, b) => (b[1] as number) - (a[1] as number))[0]?.[0] || "General";

    return {
      total,
      latestEvent,
      activeTopic
    };
  }, [competitorEvents]);

  const hasTrackedCompetitors = singleCompetitorBenchmarks.length > 0;

  return (
    <div className="space-y-6">

      {/* COMPETITOR SEARCH -- the only path onto this tab's data now. No
          candidate lists, no auto-surfaced noise: a name either matches a
          real tracked competitor, a discovered-but-unpromoted candidate, or
          triggers a scoped fresh search. */}
      <Card className={glassCard(theme)}>
        <div className={SPECULAR_LINE} />
        <CardHeader className={`pb-3 border-b ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
          <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
            <Search className="h-4 w-4 mr-2" style={{ color: accent }} />
            Search Competitors
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 space-y-4">
          <form onSubmit={handleCompetitorSearch} className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search competitor name..."
              className={`flex-1 rounded px-3 py-2 text-xs font-mono focus:outline-none ${bodyText(theme)} ${isDark ? "bg-zinc-950/60 border border-white/[0.12] placeholder:text-zinc-600 focus:border-[#00F5D4]/50" : "bg-white/60 border border-black/[0.08] placeholder:text-zinc-400 focus:border-[#3B82F6]/50"}`}
            />
            <button
              type="submit"
              disabled={searchLoading || !searchQuery.trim()}
              className={`disabled:opacity-50 disabled:cursor-not-allowed font-mono text-xs px-4 py-2 whitespace-nowrap ${glassPrimaryButton(theme)}`}
            >
              {searchLoading ? "Searching..." : "Search"}
            </button>
          </form>

          {searchErrorMsg && (
            <p className="text-red-500 font-mono text-xs">{searchErrorMsg}</p>
          )}

          {searchResult && searchResult.status === "searching" && (
            <div className={`rounded-2xl p-4 flex items-center space-x-3 border ${isDark ? "border-[#00F5D4]/30 bg-black/30" : "border-[#3B82F6]/30 bg-black/[0.03]"}`}>
              <div className="h-3 w-3 rounded-full animate-pulse" style={{ backgroundColor: accent }} />
              <p className={`text-xs font-mono ${mutedText(theme)}`}>
                Running a fresh scoped search — collecting and scoring coverage for this name. This can take a moment.
              </p>
            </div>
          )}

          {searchResult && searchResult.status === "tracked" && (
            <div className={`rounded-2xl p-4 space-y-2 border ${isDark ? "border-[#00F5D4]/30 bg-black/30" : "border-[#3B82F6]/30 bg-black/[0.03]"}`}>
              <div className="flex items-center justify-between">
                <span className={`font-mono text-sm font-bold ${bodyText(theme)}`}>{searchResult.competitor.name}</span>
                <Badge className={glassPill(theme)} style={{ color: accent }}>TRACKED</Badge>
              </div>
              {searchResult.competitor.health_status === 'INSUFFICIENT_EVIDENCE' ? (
                <p className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>
                  No qualifying coverage found yet — tracked, but not enough evidence to score
                </p>
              ) : (
                <div className="grid grid-cols-4 gap-3 text-xs font-mono">
                  <div>
                    <span className={`block ${mutedText(theme)}`}>Reputation</span>
                    <span className="font-bold text-sm" style={{ color: accent }}>
                      {searchResult.competitor.reputation_score !== null ? searchResult.competitor.reputation_score.toFixed(1) : 'N/A'}
                    </span>
                  </div>
                  <div>
                    <span className={`block ${mutedText(theme)}`}>Rank</span>
                    <span className={bodyText(theme)}>{searchResult.competitor.rank ? `#${searchResult.competitor.rank}` : 'Unranked'}</span>
                  </div>
                  <div>
                    <span className={`block ${mutedText(theme)}`}>Risk</span>
                    <span className={bodyText(theme)}>{searchResult.competitor.risk_score !== null ? searchResult.competitor.risk_score.toFixed(1) : 'N/A'}</span>
                  </div>
                  <div>
                    <span className={`block ${mutedText(theme)}`}>Share of Voice</span>
                    <span className={bodyText(theme)}>{searchResult.competitor.share_of_voice !== null ? `${searchResult.competitor.share_of_voice.toFixed(1)}%` : 'N/A'}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {searchResult && searchResult.status === "unpromoted_candidate" && (
            <div className={`rounded-2xl p-4 space-y-2 border border-amber-500/30 ${isDark ? "bg-black/30" : "bg-black/[0.03]"}`}>
              <div className="flex items-center justify-between">
                <span className={`font-mono text-sm font-bold ${bodyText(theme)}`}>{searchResult.candidate.name}</span>
                <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/30 font-mono text-xs">NOT YET TRACKED</Badge>
              </div>
              <p className={`text-xs font-mono ${mutedText(theme)}`}>
                Discovered ({searchResult.candidate.mention_count} mentions, {(searchResult.candidate.confidence * 100).toFixed(0)}% confidence) in already-collected coverage but not yet promoted — no comparison data exists for this name yet.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {!hasTrackedCompetitors && (
        <Card className={`${glassCard(theme)} h-40`}>
          <div className={SPECULAR_LINE} />
          <CardContent className="h-full flex flex-col items-center justify-center space-y-2">
            <Compass className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
            <p className={`font-mono text-xs ${mutedText(theme)}`}>No tracked competitors yet.</p>
            <p className={`font-mono text-xs ${mutedText(theme)}`}>Search a name above to start tracking a real competitor.</p>
          </CardContent>
        </Card>
      )}

      {hasTrackedCompetitors && (
      <>
      {/* SUMMARY CARD */}
      {summary && (
        <Card className={`${glassCard(theme)} font-mono`}>
          <CardHeader className={`pb-3 border-b ${cardBorder}`}>
            <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
              <Trophy className="h-4 w-4 text-[#D4AF37] mr-2" />
              Competitor Summary
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4 grid gap-4 sm:grid-cols-2 text-xs">
            <div>
              <span className={`block ${mutedText(theme)}`}>Ahead on Reputation:</span>
              <span className={`font-bold ${bodyText(theme)}`}>{summary.leader}</span>
            </div>
            <div className={`border-t pt-3 sm:border-t-0 sm:pt-0 sm:border-l sm:pl-4 ${cardBorder}`}>
              <span className={`block ${mutedText(theme)}`}>Recommendation:</span>
              <p className={`leading-normal mt-1 ${bodyText(theme)}`}>{summary.recommendation}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 1. Radar Comparison Matrix -- client vs. the one selected competitor only */}
      <ErrorBoundary fallback={<TelemetryErrorWidget title="Radar Chart Error" />}>
        {benchmarksLoading ? (
          <Card className={`${glassTokens[theme].card} rounded-3xl h-[380px] animate-pulse`} />
        ) : benchmarksError ? (
          <Card className={`${glassCard(theme)} border-red-500/20 h-[380px]`}>
            <TelemetryErrorWidget title="Radar Telemetry Offline" message={benchmarksError} />
          </Card>
        ) : (
          <Card className={glassCard(theme)}>
            <CardHeader>
              <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
                <Compass className="h-4 w-4 text-[#D4AF37] mr-2" />
                Competitor Comparison
              </CardTitle>
              <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>{activeClientName} vs. {selectedCompetitor?.name || "selected competitor"} — Reputation, Sentiment, Risk Containment, and Share of Voice</CardDescription>
            </CardHeader>
            <CardContent className="flex justify-center items-center h-[320px]">
              {selectedCompetitor && selectedCompetitor.health_status !== "INSUFFICIENT_EVIDENCE" ? (
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="80%" data={singleCompetitorRadarData}>
                    <PolarGrid stroke={isDark ? "#3f3f46" : "#d4d4d8"} />
                    <PolarAngleAxis dataKey="subject" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} stroke={isDark ? "#3f3f46" : "#d4d4d8"} tick={false} />

                    {/* CLIENT RADAR STYLING */}
                    <Radar name={activeClientName} dataKey={activeClientName} stroke="#D4AF37" fill="#D4AF37" fillOpacity={0.4} strokeWidth={3} />

                    {/* THE ONE SELECTED COMPETITOR */}
                    <Radar name={selectedCompetitor.name} dataKey={selectedCompetitor.name} stroke="#38BDF8" fill="#38BDF8" fillOpacity={0.15} strokeWidth={2} />
                    <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b', borderRadius: '6px', fontFamily: 'monospace', fontSize: 12 }} />
                  </RadarChart>
                </ResponsiveContainer>
              ) : (
                <div className={`font-mono text-xs text-center ${mutedText(theme)}`}>
                  Waiting for verified competitor data.
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </ErrorBoundary>

      <div className="grid gap-6 md:grid-cols-2">
        
        {/* Reputation Compare Chart */}
        <ErrorBoundary fallback={<TelemetryErrorWidget title="Compare Chart Error" />}>
          {benchmarksLoading ? (
            <Card className={`${glassTokens[theme].card} rounded-3xl h-[320px] animate-pulse`}>
              <CardContent className="h-[240px] bg-[#1E293B]/10 rounded m-4" />
            </Card>
          ) : benchmarksError ? (
            <Card className={`${glassCard(theme)} border-red-500/20 h-[320px]`}>
              <TelemetryErrorWidget title="Competitor Metrics Offline" message={benchmarksError} />
            </Card>
          ) : (
            <Card className={glassCard(theme)}>
              <CardHeader>
                <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
                  <BarChart3 className="h-4 w-4 text-[#D4AF37] mr-2" />
                  Reputation Compare
                </CardTitle>
              </CardHeader>
              <CardContent className="pl-2">
                <div className="h-[260px]">
                  {singleCompetitorBenchmarks.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                          data={[
                          { name: activeClientName, Score: reputation?.score ?? 0 },
                          ...singleCompetitorBenchmarks.map((b) => ({
                              name: b.competitor_name,
                              Score: b.reputation
                          }))
                          ]}
                          margin={{ top: 10, right: 30, left: 10, bottom: 5 }}
                      >
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                          <XAxis dataKey="name" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                          <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} domain={[0, 100]} />
                          <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b' }} />
                          <Bar dataKey="Score" fill="#D4AF37" radius={[3, 3, 0, 0]} />
                      </BarChart>
                      </ResponsiveContainer>
                  ) : (
                      <div className="flex flex-col items-center justify-center h-full space-y-2">
                        <BarChart3 className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
                        <p className={`font-mono text-xs ${mutedText(theme)}`}>Waiting for verified competitor data.</p>
                      </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </ErrorBoundary>

        {/* Share of Voice Chart */}
        <ErrorBoundary fallback={<TelemetryErrorWidget title="SOV Chart Error" />}>
          {benchmarksLoading ? (
            <Card className={`${glassTokens[theme].card} rounded-3xl h-[320px] animate-pulse`}>
              <CardContent className="h-[240px] bg-[#1E293B]/10 rounded m-4" />
            </Card>
          ) : benchmarksError ? (
            <Card className={`${glassCard(theme)} border-red-500/20 h-[320px]`}>
              <TelemetryErrorWidget title="Competitor SOV Offline" message={benchmarksError} />
            </Card>
          ) : (
            <Card className={glassCard(theme)}>
              <CardHeader>
                <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
                  <Users className="h-4 w-4 text-blue-500 mr-2" />
                  Share of Voice (SOV)
                </CardTitle>
              </CardHeader>
              <CardContent className="pl-2">
                <div className="h-[260px]">
                  {singleCompetitorBenchmarks.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                          data={[
                          {
                              name: activeClientName,
                              'Share of Voice': calculateClientSOV(singleCompetitorBenchmarks)
                          },
                          ...singleCompetitorBenchmarks.map((b) => ({
                              name: b.competitor_name,
                              'Share of Voice': b.sov
                          }))
                          ]}
                          margin={{ top: 10, right: 30, left: 10, bottom: 5 }}
                      >
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                          <XAxis dataKey="name" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                          <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} domain={[0, 100]} />
                          <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b' }} />
                          <Bar dataKey="Share of Voice" fill="#38BDF8" radius={[3, 3, 0, 0]} />
                      </BarChart>
                      </ResponsiveContainer>
                  ) : (
                      <div className="flex flex-col items-center justify-center h-full space-y-2">
                        <Users className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
                        <p className={`font-mono text-xs ${mutedText(theme)}`}>Waiting for verified competitor data.</p>
                      </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </ErrorBoundary>
      </div>

      {/* COMPETITIVE LANDSCAPE INDEX removed per hyperfocus redesign -- a
          multi-brand ranking table has no place in a view scoped to exactly
          one client + one competitor. Its only helper, getThreatLevel, was
          removed with it (verified unused elsewhere before deleting). */}

      {/* ACTIVITY SUMMARY CARD */}
      <Card className={`${glassCard(theme)} font-mono`}>
        <CardHeader className={`pb-3 border-b ${cardBorder}`}>
          <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
            <Activity className="h-4 w-4 text-[#D4AF37] mr-2" />
            Competitive Activity
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 grid gap-4 sm:grid-cols-3 text-xs">
          <div>
            <span className={`block ${mutedText(theme)}`}>Events Analysed:</span>
            <span className={`font-bold ${bodyText(theme)}`}>{activitySummary.total}</span>
          </div>
          <div>
            <span className={`block ${mutedText(theme)}`}>Latest Event:</span>
            <span className={`font-bold ${bodyText(theme)}`}>{activitySummary.latestEvent}</span>
          </div>
          <div>
            <span className={`block ${mutedText(theme)}`}>Most Active Topic:</span>
            <span className={`font-bold ${bodyText(theme)}`}>{activitySummary.activeTopic}</span>
          </div>
        </CardContent>
      </Card>

      {/* COMPETITOR ACTIVITY TABLE -- events for the one selected
          competitor only (competitorEvents is already scoped above). */}
      <Card className={glassCard(theme)}>
        <CardHeader>
          <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center justify-between`}>
            <div className="flex items-center">
              <Search className="h-4 w-4 text-[#38BDF8] mr-2" />
              Competitor Activity — {selectedCompetitor?.name}
            </div>
            <Badge className="bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30 font-mono text-xs">
              {competitorEvents.length} Events
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader className={`${rowBorder} ${tableHeaderBg}`}>
              <TableRow className={rowBorder}>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>COMPETITOR</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>EVENT HEADLINE</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>BUSINESS TOPIC</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>REPUTATION IMPACT</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>RISK SCORE</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>SOURCE</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>PUBLISHED DATE</TableHead>
                <TableHead className={`font-mono text-xs text-right ${mutedText(theme)}`}>ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {competitorEvents.map((doc, idx) => (
                <TableRow key={doc.id} className={`${rowBorder} ${rowHoverBg} transition-colors cursor-pointer`} onClick={() => setSelectedDocId(doc.id)}>
                  <TableCell className={`font-mono text-xs font-bold ${bodyText(theme)}`}>{doc.matchedCompetitor}</TableCell>
                  <TableCell className={`font-mono text-xs max-w-[280px] truncate ${bodyText(theme)}`}>{doc.title}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className="border-[#D4AF37]/30 text-[#D4AF37] font-mono text-xs bg-[#D4AF37]/5">
                      {doc.topic}
                    </Badge>
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
              {competitorEvents.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className={`text-center py-10 font-mono text-xs ${mutedText(theme)}`}>
                    No competitor events recorded.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      </>
      )}

      {/* Details Drawer (Slide-Over Panel) -- kept high-opacity (not the
          standard glass alpha) for the same legibility reason as RiskTab.tsx's
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
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Matched Brand: {selectedDoc.matchedCompetitor}</span>
                  </div>
                </div>

                {/* Risk score calculation breakdown */}
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
                      <span className={mutedText(theme)}>Sentiment:</span>
                      <span className={bodyText(theme)}>{selectedDoc.sentiment?.toFixed(2) || "0.00"}</span>
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

                {/* Detected Entities */}
                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold ${mutedText(theme)}`}>Extracted Named Entities</span>
                  <div className="flex flex-wrap gap-2">
                    {selectedDoc.extracted_entities && selectedDoc.extracted_entities.length > 0 ? (
                      selectedDoc.extracted_entities.map((ent: any, idx: number) => (
                        <Badge key={idx} variant="outline" className="border-blue-500/30 text-blue-500 text-xs bg-blue-500/5">
                          {ent.name} ({ent.entity_type})
                        </Badge>
                      ))
                    ) : (
                      <span className={`text-xs ${mutedText(theme)}`}>No matching corporate entities identified.</span>
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
