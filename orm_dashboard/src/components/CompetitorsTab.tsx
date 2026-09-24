import React, { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { 
  Compass, Users, BarChart3, Search, ShieldCheck,
  Info, Calendar, AlertOctagon, X, ExternalLink
} from "lucide-react";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { calculateClientSOV } from "@/utils/shareOfVoice";
import { formatScore, tooltipScoreFormatter } from "@/utils/formatScore";
import { fetchDocumentDetails, searchCompetitor, fetchTopicDistribution } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, glassPill, glassPrimaryButton, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { ProductCompareSection } from "@/components/ProductCompareSection";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { CompetitorRadarAxesDefinition, ReputationScoreDefinition, ShareOfVoiceDefinition, TopicOwnershipDefinition } from "@/lib/metricDefinitions";

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
  // Fixed palette for the Topic Ownership chart -- up to 17 taxonomy
  // categories can appear as stacked segments, each needing a distinct,
  // stable-per-render color (the client's own gold/accent styling used
  // elsewhere on this page is reserved for its own dedicated cases, so this
  // is a separate palette rather than reusing #D4AF37/accent here).
  const TOPIC_COLORS = ["#D4AF37", "#38BDF8", "#F97316", "#A78BFA", "#34D399", "#F472B6", "#FBBF24", "#60A5FA", "#EF4444", "#14B8A6", "#8B5CF6", "#EAB308", "#EC4899", "#22D3EE", "#84CC16", "#F87171", "#94A3B8"];
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

  // Topic Ownership (Part O/R): independent fetch, not threaded through the
  // parent like benchmarks/normalizedBenchmarks -- this is a new, on-demand
  // endpoint (client-intelligence/{id}/topic-distribution) nothing else on
  // the dashboard needs, so it's fetched directly here rather than adding a
  // new prop plumbed through useDashboardData for a single consumer.
  const [topicDistribution, setTopicDistribution] = useState<any[]>([]);
  const [topicDistLoading, setTopicDistLoading] = useState(false);
  const [topicDistError, setTopicDistError] = useState<string | null>(null);

  useEffect(() => {
    if (!clientId) {
      setTopicDistribution([]);
      return;
    }
    let cancelled = false;
    setTopicDistLoading(true);
    setTopicDistError(null);
    fetchTopicDistribution(clientId)
      .then(data => { if (!cancelled) setTopicDistribution(data?.entities || []); })
      .catch(() => { if (!cancelled) { setTopicDistribution([]); setTopicDistError("Telemetry Offline"); } })
      .finally(() => { if (!cancelled) setTopicDistLoading(false); });
    return () => { cancelled = true; };
  }, [clientId]);

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

  // Reset search state whenever the active client changes (Part L
  // forensics, 2026-09-22): this component stays mounted across a client
  // switch -- only activeTab, not clientId, gates whether it's rendered
  // (dashboard/page.tsx:369-385) -- so without this, a search result for
  // the previous client stayed on screen after switching to a new one, and
  // an in-flight poll for the previous client could still land later and
  // overwrite the new client's view with stale data. The unmount-only
  // cleanup above still handles the tab-switch-and-back case unchanged;
  // this is a second, narrower reset for staying on this tab while
  // switching clients.
  useEffect(() => {
    searchPollRef.current.cancelled = true;
    setSearchQuery("");
    setSearchResult(null);
    setSearchLoading(false);
    setSearchErrorMsg(null);
  }, [clientId]);

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
    // C6: was calculateClientSOV(singleCompetitorBenchmarks) -- the
    // hyperfocus redesign narrowed that array to just the one currently
    // searched competitor, so "100 - this one competitor's SOV" silently
    // overstated the client's share whenever other tracked competitors also
    // held real share. normalizedBenchmarks (already fetched/computed
    // upstream in useAnalytics.ts and threaded in as a prop, just unused
    // here until now) holds every tracked competitor's row, which is what
    // the client's own remaining share must be derived against (Part O/Part
    // 1 fix). Identical result to before for a client with exactly one
    // tracked competitor, since normalizedBenchmarks then has that one row.
    data[3][activeClientName] = calculateClientSOV(normalizedBenchmarks);

    if (selectedCompetitor) {
      data[0][selectedCompetitor.name] = selectedCompetitor.reputation_score ?? 0;
      data[1][selectedCompetitor.name] = ((selectedCompetitor.sentiment_score ?? 0) + 1) * 50;
      data[2][selectedCompetitor.name] = 100 - (selectedCompetitor.risk_score ?? 0);
      data[3][selectedCompetitor.name] = selectedCompetitor.share_of_voice ?? 0;
    }
    return data;
  }, [activeClientName, reputation, repBreakdown, selectedCompetitor, normalizedBenchmarks]);

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

  const hasTrackedCompetitors = singleCompetitorBenchmarks.length > 0;

  // 7. TOPIC OWNERSHIP -- Part O/R. Same near-zero-category display floor as
  // Coverage-by-Topic (useAnalytics.ts, MIN_TOPIC_DOCUMENT_COUNT): a shared
  // 17-topic taxonomy across every client means a document can land under a
  // structurally-irrelevant category for this client, so a topic with almost
  // no real representation across the entities being compared is filtered
  // from the chart rather than shown as if it were meaningful. Scoped to
  // this comparison (total across only the entities with qualifying
  // evidence), not the whole platform-wide threshold, since this is a
  // narrower view than that chart.
  const MIN_TOPIC_COMPARISON_COUNT = 5;

  // Scoped to exactly the same [client, selectedCompetitor] pair every
  // other comparison card on this page uses (Competitor Comparison radar,
  // Reputation Compare, the pairwise SOV chart) -- not the multi-competitor
  // head-to-head view's broader scope. The /topic-distribution endpoint
  // still returns every tracked competitor in one call (same shape as
  // /benchmark), filtered down here client-side, the same division of
  // labour singleCompetitorBenchmarks already uses above for the identical
  // pairwise-vs-broad-fetch situation.
  const pairScopedTopicDistribution = useMemo(() => {
    if (!selectedCompetitor) return [];
    return (topicDistribution || []).filter(
      e => e && (e.is_client || e.entity_id === selectedCompetitor.entity_id)
    );
  }, [topicDistribution, selectedCompetitor]);

  const topicOwnershipData = useMemo(() => {
    const withEvidence = (pairScopedTopicDistribution || []).filter(e => e && e.total_documents > 0);
    if (withEvidence.length === 0) return { chartData: [], topicKeys: [], entityNames: [] };

    const topicTotals: Record<string, number> = {};
    withEvidence.forEach(e => {
      Object.entries(e.topic_counts || {}).forEach(([topic, count]) => {
        topicTotals[topic] = (topicTotals[topic] || 0) + (count as number);
      });
    });
    const topicKeys = Object.entries(topicTotals)
      .filter(([, total]) => total >= MIN_TOPIC_COMPARISON_COUNT)
      .sort((a, b) => b[1] - a[1])
      .map(([topic]) => topic);

    const chartData = withEvidence.map(e => {
      const row: any = { name: e.name, isClient: e.is_client, total: e.total_documents };
      topicKeys.forEach(topic => {
        const count = (e.topic_counts || {})[topic] || 0;
        row[topic] = e.total_documents > 0 ? (count / e.total_documents) * 100 : 0;
      });
      return row;
    });

    return { chartData, topicKeys, entityNames: withEvidence.map(e => e.name) };
  }, [pairScopedTopicDistribution]);

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
              className={`flex-1 rounded px-3 py-2 min-h-11 text-xs font-mono focus:outline-none ${bodyText(theme)} ${isDark ? "bg-zinc-950/60 border border-white/[0.12] placeholder:text-zinc-600 focus:border-[#00F5D4]/50" : "bg-white/60 border border-black/[0.08] placeholder:text-zinc-400 focus:border-[#3B82F6]/50"}`}
            />
            <button
              type="submit"
              disabled={searchLoading || !searchQuery.trim()}
              className={`disabled:opacity-50 disabled:cursor-not-allowed font-mono text-xs px-4 py-2 min-h-11 whitespace-nowrap ${glassPrimaryButton(theme)}`}
            >
              {searchLoading ? "Searching..." : "Search"}
            </button>
          </form>
          {/* Same disambiguation already on the Dashboard's Overview
              paragraph for the #17/share-of-voice figure -- surfaced here
              too so a viewer who lands on this page first (before ever
              seeing the Dashboard) isn't left wondering why that ranking
              doesn't show up on this page (ui_redesign_plan.md #8). */}
          <p className={`text-[11px] font-mono leading-relaxed ${mutedText(theme)}`}>
            Your passive market ranking (shown on your Dashboard) comes from general coverage. This page shows head-to-head comparisons only for competitors you add here.
          </p>

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
                      {searchResult.competitor.reputation_score !== null ? searchResult.competitor.reputation_score.toFixed(2) : 'N/A'}
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
                <InfoTooltip label="About these metrics"><CompetitorRadarAxesDefinition /></InfoTooltip>
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
                    <Tooltip formatter={tooltipScoreFormatter} contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b', borderRadius: '6px', fontFamily: 'monospace', fontSize: 12 }} />
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
                  <InfoTooltip label="About Reputation Score"><ReputationScoreDefinition /></InfoTooltip>
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
                          <Tooltip formatter={tooltipScoreFormatter} contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b' }} />
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
                  <InfoTooltip label="About Share of Voice"><ShareOfVoiceDefinition /></InfoTooltip>
                </CardTitle>
                {/* Part 2: disambiguates this pairwise chart from the
                    Overall Share of Voice tile below, which is the client's
                    real share across every tracked competitor, not just
                    this one. */}
                <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>vs. {selectedCompetitor?.name || "selected competitor"} only</CardDescription>
              </CardHeader>
              <CardContent className="pl-2">
                <div className="h-[260px]">
                  {singleCompetitorBenchmarks.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                          data={[
                          {
                              name: activeClientName,
                              'Share of Voice': calculateClientSOV(normalizedBenchmarks)
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
                          <Tooltip formatter={tooltipScoreFormatter} contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b' }} />
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

      {/* OVERALL SHARE OF VOICE TILE -- Part 2. Distinct from the pairwise
          "Share of Voice (SOV)" chart above (client vs. just the one
          searched competitor): this is the client's real remaining share
          once every tracked competitor's SOV is accounted for, not just
          the one currently in focus (Part 1's fix / Part O finding).
          Reuses the same card styling as the Competitor Summary card
          above rather than introducing new visual treatment. */}
      {!benchmarksLoading && !benchmarksError && (
        <Card className={`${glassCard(theme)} font-mono`}>
          <CardHeader className={`pb-3 border-b ${cardBorder}`}>
            <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
              <Users className="h-4 w-4 text-blue-500 mr-2" />
              Overall Share of Voice
              <InfoTooltip label="About Overall Share of Voice"><ShareOfVoiceDefinition /></InfoTooltip>
            </CardTitle>
            <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>
              Across all {normalizedBenchmarks.length} tracked competitor{normalizedBenchmarks.length === 1 ? "" : "s"} -- not just {selectedCompetitor?.name || "the one selected above"}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            {normalizedBenchmarks.length > 0 ? (
              <span className="font-bold text-2xl" style={{ color: accent }}>
                {calculateClientSOV(normalizedBenchmarks).toFixed(1)}%
              </span>
            ) : (
              <p className={`text-xs font-mono ${mutedText(theme)}`}>Waiting for verified competitor data.</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* COMPETITIVE LANDSCAPE INDEX removed per hyperfocus redesign -- a
          multi-brand ranking table has no place in a view scoped to exactly
          one client + one competitor. Its only helper, getThreatLevel, was
          removed with it (verified unused elsewhere before deleting). */}

      {/* TOPIC OWNERSHIP -- Part O/R, the last item from the original
          industry-benchmarking research. Scoped to exactly [client,
          selectedCompetitor] -- the same single pair the Competitor
          Comparison radar and Reputation Compare / Share of Voice charts
          above already use, not the multi-competitor head-to-head view's
          broader scope. The caveat below is required, not optional -- this
          is the one view on this page most likely to expose the
          shared-taxonomy classifier's known calibration limits, so it
          stays visible on the card itself, not just inside the InfoTooltip
          a viewer might not open. */}
      <ErrorBoundary fallback={<TelemetryErrorWidget title="Topic Ownership Chart Error" />}>
        {topicDistLoading ? (
          <Card className={`${glassTokens[theme].card} rounded-3xl h-[380px] animate-pulse`} />
        ) : topicDistError ? (
          <Card className={`${glassCard(theme)} border-red-500/20 h-[380px]`}>
            <TelemetryErrorWidget title="Topic Ownership Offline" message={topicDistError} />
          </Card>
        ) : (
          <Card className={glassCard(theme)}>
            <CardHeader>
              <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
                <BarChart3 className="h-4 w-4 text-[#D4AF37] mr-2" />
                Topic Ownership
                <InfoTooltip label="About Topic Ownership"><TopicOwnershipDefinition /></InfoTooltip>
              </CardTitle>
              <CardDescription className={`text-xs font-mono ${mutedText(theme)}`}>
                {activeClientName} vs. {selectedCompetitor?.name || "selected competitor"} — share of each entity&apos;s coverage by topic, last 30 days
              </CardDescription>
              <p className={`text-[11px] font-mono leading-relaxed mt-2 ${mutedText(theme)}`}>
                Uses a shared 17-topic taxonomy applied identically across every client — a category can read as
                structurally irrelevant for this client&apos;s industry. Treat this chart as directional, not precise.
              </p>
            </CardHeader>
            <CardContent className="pt-4">
              {topicOwnershipData.chartData.length > 0 ? (
                <div className="h-[360px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={topicOwnershipData.chartData} margin={{ top: 10, right: 30, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                      <XAxis dataKey="name" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} />
                      <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={11} domain={[0, 100]} unit="%" />
                      <Tooltip
                        formatter={(value: any, name: any) => [`${Number(value).toFixed(1)}%`, name]}
                        contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b', borderRadius: '6px', fontFamily: 'monospace', fontSize: 12 }}
                      />
                      <Legend wrapperStyle={{ fontFamily: 'monospace', fontSize: 10 }} />
                      {topicOwnershipData.topicKeys.map((topic, idx) => (
                        <Bar key={topic} dataKey={topic} stackId="topics" fill={TOPIC_COLORS[idx % TOPIC_COLORS.length]} />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-[200px] space-y-2">
                  <BarChart3 className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
                  <p className={`font-mono text-xs ${mutedText(theme)}`}>
                    Not enough qualifying coverage in the last 30 days to compare topics for this pair yet.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </ErrorBoundary>

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
          <div className="max-h-[420px] overflow-y-auto overflow-x-hidden">
          <Table>
            <TableHeader className={`${rowBorder} ${tableHeaderBg} sticky top-0 z-10`}>
              <TableRow className={rowBorder}>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>COMPETITOR</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>EVENT HEADLINE</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>BUSINESS TOPIC</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>SOURCE</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>PUBLISHED DATE</TableHead>
                <TableHead className={`font-mono text-xs text-right ${mutedText(theme)}`}>DETAILS</TableHead>
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
                  <TableCell colSpan={6} className={`text-center py-10 font-mono text-xs ${mutedText(theme)}`}>
                    No competitor events recorded.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          </div>
        </CardContent>
      </Card>
      </>
      )}

      {/* PRODUCT COMPARE -- below the Competitor Compare view (Product
          Compare task, Part 2). Needs a tracked competitor to know which
          competitor's product to search under, so it only renders once a
          search above has resolved to one. */}
      {selectedCompetitor && (
        <ProductCompareSection
          clientId={clientId}
          activeClientName={activeClientName}
          competitorEntityId={selectedCompetitor.entity_id}
          competitorName={selectedCompetitor.name}
        />
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
              <div className="flex-1 overflow-y-auto overflow-x-hidden p-6 space-y-6">

                {/* Headline & Meta */}
                <div className="space-y-2">
                  <h3 className={`text-sm font-bold leading-snug ${bodyText(theme)}`}>{selectedDoc.title}</h3>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Source: {selectedDoc.source}</span>
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Topic: {selectedDoc.topic}</span>
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Matched Brand: {selectedDoc.matchedCompetitor}</span>
                  </div>
                </div>

                {/* Original Article Content */}
                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold flex items-center ${mutedText(theme)}`}>
                    <Info className="h-3.5 w-3.5 mr-1 text-[#D4AF37]" /> Original Article Snippet
                  </span>
                  <div className={`border p-4 rounded text-xs leading-relaxed max-h-48 overflow-y-auto overflow-x-hidden whitespace-pre-wrap ${mutedText(theme)} ${surfaceBorder} ${surfaceBg}`}>
                    {selectedDoc.original_content || "No original content available."}
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
