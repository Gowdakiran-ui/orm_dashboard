import React, { useState, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { 
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer 
} from 'recharts';
import { 
  Compass, Users, BarChart3, Search, AlertTriangle, ShieldCheck, 
  Trophy, Info, Activity, Calendar, AlertOctagon, X, ExternalLink
} from "lucide-react";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";
import { calculateClientSOV } from "@/utils/shareOfVoice";

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
  documents
}: CompetitorsTabProps) {
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

  // 1. COMPREHENSIVE BRAND LIST FOR DISPLAY
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
    const clientSOV = calculateClientSOV(normalizedBenchmarks);

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
      ...(normalizedBenchmarks || []).map(b => ({
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
  }, [activeClientName, reputation, repBreakdown, normalizedBenchmarks, clientRank]);

  // 2. EXECUTIVE COMPETITIVE SUMMARY
  const summary = useMemo(() => {
    // C4: same fix as the landscape table below — rankedBrands always
    // includes the client row, so this must gate on competitor presence,
    // not rankedBrands.length, or a client-only "summary" (leader = self,
    // closest threat = N/A) renders as if it were a real comparison.
    if (normalizedBenchmarks.length === 0) return null;

    // Leader (Highest Reputation Score)
    const leader = [...rankedBrands].sort((a, b) => b.reputation - a.reputation)[0];

    // Share of Voice leader
    const highestSOV = [...rankedBrands].sort((a, b) => b.sov - a.sov)[0];

    // Sentiment leader
    const highestSentiment = [...rankedBrands].sort((a, b) => b.sentiment - a.sentiment)[0];

    // Highest Risk Competitor (excluding client)
    const competitorsList = rankedBrands.filter(b => !b.isClient);
    const highestRiskComp = competitorsList.length > 0 
      ? [...competitorsList].sort((a, b) => b.risk - a.risk)[0]
      : null;

    // Closest Competitor (closest reputation score to client)
    const clientBrand = rankedBrands.find(b => b.isClient);
    let closestComp: any = null;
    if (clientBrand && competitorsList.length > 0) {
      let minDiff = Infinity;
      competitorsList.forEach(c => {
        const diff = Math.abs(c.reputation - clientBrand.reputation);
        if (diff < minDiff) {
          minDiff = diff;
          closestComp = c;
        }
      });
    }

    // Recommendation logic based on scores
    let recommendation = "Maintain market visibility and monitor key brand metrics.";
    if (clientBrand && leader && leader.isClient) {
      recommendation = `Maintain market leadership by prioritizing high-sentiment narrative tracks. Monitor ${closestComp ? closestComp.name : "competitors"} closely.`;
    } else if (clientBrand && leader && !leader.isClient) {
      recommendation = `Increase visibility and address sentiment deficits to close the gap with Market Leader ${leader.name}.`;
    }
    if (highestRiskComp && highestRiskComp.risk > 40) {
      recommendation += ` Watch ${highestRiskComp.name} for volatile risk escalations.`;
    }

    return {
      leader: leader?.name || "N/A",
      closestThreat: closestComp ? (closestComp as any).name : "N/A",
      highestSOV: `${highestSOV?.name || "N/A"} (${(highestSOV?.sov ?? 0).toFixed(0)}%)`,
      highestSentiment: highestSentiment?.name || "N/A",
      highestRisk: highestRiskComp ? `${highestRiskComp.name} (Risk: ${highestRiskComp.risk.toFixed(0)})` : "N/A",
      fastestRising: "Insufficient historical data", 
      recommendation
    };
  }, [rankedBrands, normalizedBenchmarks]);

  // 3. THREAT LEVEL COLUMN CALCULATION (Dynamic Indexing)
  // Threat Index Formula = (Competitor SOV * 0.40) + ((100 - Competitor Reputation) * 0.30) + (Competitor Risk * 0.30)
  const getThreatLevel = (sov: number, reputation: number, risk: number) => {
    const index = (sov * 0.4) + ((100 - reputation) * 0.3) + (risk * 0.3);
    if (index >= 75) return { label: "CRITICAL", class: "bg-red-500/10 text-red-400 border border-red-500/30" };
    if (index >= 50) return { label: "HIGH", class: "bg-orange-500/10 text-orange-400 border border-orange-500/30" };
    if (index >= 25) return { label: "MEDIUM", class: "bg-yellow-500/10 text-yellow-400 border border-yellow-500/30" };
    return { label: "LOW", class: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30" };
  };

  // 4. VERIFIED COMPETITOR EVENTS FILTERING
  const competitorNames = useMemo(() => {
    return (normalizedBenchmarks || []).map(b => b.competitor_name.toLowerCase());
  }, [normalizedBenchmarks]);

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
        const matchedComp = (normalizedBenchmarks || []).find(b =>
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
  }, [documents, competitorNames, normalizedBenchmarks]);

  const selectedDoc = useMemo(() => {
    if (!selectedDocId) return null;
    return competitorEvents.find(d => d.id === selectedDocId) || null;
  }, [selectedDocId, competitorEvents]);

  // 5. EXECUTIVE ACTIVITY SUMMARY STATS
  const activitySummary = useMemo(() => {
    const total = competitorEvents.length;
    if (total === 0) {
      return {
        total: 0,
        highestImpact: "Insufficient historical data",
        mostMentioned: "Insufficient historical data",
        latestEvent: "Insufficient historical data",
        activeTopic: "Insufficient historical data"
      };
    }

    // Highest impact competitor (highest reputation score)
    const highestImpComp = (normalizedBenchmarks || []).reduce((max, b) => 
      (b.reputation ?? 0) > (max.reputation ?? 0) ? b : max
    , normalizedBenchmarks[0]);

    // Most mentioned competitor (by document occurrences)
    const compCounts = competitorEvents.reduce((acc, curr) => {
      acc[curr.matchedCompetitor] = (acc[curr.matchedCompetitor] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);
    const mostMentioned = Object.entries(compCounts).sort((a, b) => (b[1] as number) - (a[1] as number))[0]?.[0] || "N/A";

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
      highestImpact: highestImpComp ? highestImpComp.competitor_name : "N/A",
      mostMentioned,
      latestEvent,
      activeTopic
    };
  }, [competitorEvents, normalizedBenchmarks]);

  return (
    <div className="space-y-6">
      
      {/* EXECUTIVE SUMMARY CARD */}
      {summary && (
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl font-mono">
          <CardHeader className="pb-3 border-b border-[#1F2937]/40">
            <CardTitle className="text-xs uppercase tracking-wider text-slate-400 flex items-center">
              <Trophy className="h-4 w-4 text-[#D4AF37] mr-2" />
              COMPETITIVE INTELLIGENCE SUMMARY
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4 grid gap-4 sm:grid-cols-2 md:grid-cols-3 text-[10px]">
            <div>
              <span className="text-slate-500 block">Market Leader:</span>
              <span className="text-slate-200 font-bold">{summary.leader}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Closest Threat:</span>
              <span className="text-slate-200 font-bold">{summary.closestThreat}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Highest Share of Voice:</span>
              <span className="text-slate-200 font-bold">{summary.highestSOV}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Strongest Sentiment:</span>
              <span className="text-slate-200 font-bold">{summary.highestSentiment}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Highest Risk Competitor:</span>
              <span className="text-slate-200 font-bold">{summary.highestRisk}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Fastest Rising Competitor:</span>
              <span className="text-slate-400 italic">{summary.fastestRising}</span>
            </div>
            <div className="sm:col-span-2 md:col-span-3 border-t border-[#1F2937]/30 pt-3">
              <span className="text-slate-500 block">Recommendation:</span>
              <p className="text-slate-300 leading-normal mt-1">{summary.recommendation}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 1. Radar Comparison Matrix */}
      <ErrorBoundary fallback={<TelemetryErrorWidget title="Radar Chart Error" />}>
        {benchmarksLoading ? (
          <Card className="bg-[#060B18]/60 border-[#1F2937]/60 h-[380px] animate-pulse" />
        ) : benchmarksError ? (
          <Card className="bg-[#060B18]/60 border-red-500/20 h-[380px]">
            <TelemetryErrorWidget title="Radar Telemetry Offline" message={benchmarksError} />
          </Card>
        ) : (
          <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
            <CardHeader>
              <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
                <Compass className="h-4 w-4 text-[#D4AF37] mr-2" />
                Executive Competitor Radar Matrix
              </CardTitle>
              <CardDescription className="text-[10px] font-mono text-slate-500">Multi-dimensional brand equity comparison overlaying Reputation, Sentiment, Risk Containment, and SOV</CardDescription>
            </CardHeader>
            <CardContent className="flex justify-center items-center h-[320px]">
              {benchmarks.length >= 2 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="80%" data={competitorRadarData}>
                    <PolarGrid stroke="#1F2937" />
                    <PolarAngleAxis dataKey="subject" stroke="#94A3B8" fontSize={10} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} stroke="#1F2937" tick={false} />
                    
                    {/* CLIENT RADAR STYLING */}
                    <Radar name={activeClientName} dataKey={activeClientName} stroke="#D4AF37" fill="#D4AF37" fillOpacity={0.4} strokeWidth={3} />
                    
                    {/* COMPETITOR RADARS */}
                    {normalizedBenchmarks.map((b, idx) => {
                      const colors = ["#38BDF8", "#EF4444", "#EAB308", "#10B981"];
                      const col = colors[idx % colors.length];
                      return (
                        <Radar key={idx} name={b.competitor_name} dataKey={b.competitor_name} stroke={col} fill={col} fillOpacity={0.02} strokeWidth={1.5} />
                      );
                    })}
                    <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff', borderRadius: '6px', fontFamily: 'monospace', fontSize: 11 }} />
                  </RadarChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-slate-500 font-mono text-xs text-center">
                  Waiting for verified competitor intelligence.
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
            <Card className="bg-[#060B18]/60 border-[#1F2937]/60 h-[320px] animate-pulse">
              <CardContent className="h-[240px] bg-[#1E293B]/10 rounded m-4" />
            </Card>
          ) : benchmarksError ? (
            <Card className="bg-[#060B18]/60 border-red-500/20 h-[320px]">
              <TelemetryErrorWidget title="Competitor Metrics Offline" message={benchmarksError} />
            </Card>
          ) : (
            <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
              <CardHeader>
                <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
                  <BarChart3 className="h-4 w-4 text-[#D4AF37] mr-2" />
                  REPUTATION COMPARE
                </CardTitle>
              </CardHeader>
              <CardContent className="pl-2">
                <div className="h-[260px]">
                  {benchmarks.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                      <BarChart 
                          data={[
                          { name: activeClientName, Score: reputation?.score ?? 0 },
                          ...benchmarks.map((b) => ({
                              name: b.competitor_name,
                              Score: b.reputation
                          }))
                          ]} 
                          margin={{ top: 10, right: 30, left: 10, bottom: 5 }}
                      >
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                          <XAxis dataKey="name" stroke="#94A3B8" fontSize={10} />
                          <YAxis stroke="#94A3B8" fontSize={10} domain={[0, 100]} />
                          <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff' }} />
                          <Bar dataKey="Score" fill="#D4AF37" radius={[3, 3, 0, 0]} />
                      </BarChart>
                      </ResponsiveContainer>
                  ) : (
                      <div className="flex flex-col items-center justify-center h-full space-y-2">
                        <BarChart3 className="h-6 w-6 text-slate-500 opacity-60" />
                        <p className="text-slate-500 font-mono text-xs">Waiting for verified competitor intelligence.</p>
                      </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </ErrorBoundary>

        {/* SOV Chart */}
        <ErrorBoundary fallback={<TelemetryErrorWidget title="SOV Chart Error" />}>
          {benchmarksLoading ? (
            <Card className="bg-[#060B18]/60 border-[#1F2937]/60 h-[320px] animate-pulse">
              <CardContent className="h-[240px] bg-[#1E293B]/10 rounded m-4" />
            </Card>
          ) : benchmarksError ? (
            <Card className="bg-[#060B18]/60 border-red-500/20 h-[320px]">
              <TelemetryErrorWidget title="Competitor SOV Offline" message={benchmarksError} />
            </Card>
          ) : (
            <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
              <CardHeader>
                <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
                  <Users className="h-4 w-4 text-blue-400 mr-2" />
                  SHARE OF VOICE (SOV)
                </CardTitle>
              </CardHeader>
              <CardContent className="pl-2">
                <div className="h-[260px]">
                  {benchmarks.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                      <BarChart 
                          data={[
                          { 
                              name: activeClientName, 
                              'Share of Voice': calculateClientSOV(normalizedBenchmarks)
                          },
                          ...normalizedBenchmarks.map((b) => ({
                              name: b.competitor_name,
                              'Share of Voice': b.sov
                          }))
                          ]} 
                          margin={{ top: 10, right: 30, left: 10, bottom: 5 }}
                      >
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                          <XAxis dataKey="name" stroke="#94A3B8" fontSize={10} />
                          <YAxis stroke="#94A3B8" fontSize={10} domain={[0, 100]} />
                          <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff' }} />
                          <Bar dataKey="Share of Voice" fill="#38BDF8" radius={[3, 3, 0, 0]} />
                      </BarChart>
                      </ResponsiveContainer>
                  ) : (
                      <div className="flex flex-col items-center justify-center h-full space-y-2">
                        <Users className="h-6 w-6 text-slate-500 opacity-60" />
                        <p className="text-slate-500 font-mono text-xs">Waiting for verified competitor intelligence.</p>
                      </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </ErrorBoundary>
      </div>

      {/* Benchmark Telemetry Details */}
      <ErrorBoundary fallback={<TelemetryErrorWidget title="Landscape Index Error" />}>
        {benchmarksLoading ? (
          <Card className="bg-[#060B18]/60 border-[#1F2937]/60 h-60 animate-pulse">
            <CardHeader className="space-y-2">
              <div className="h-4 bg-[#1E293B] rounded w-1/4" />
            </CardHeader>
            <CardContent className="space-y-4">
              {[1, 2].map(x => (
                <div key={x} className="h-8 bg-[#1E293B]/10 rounded" />
              ))}
            </CardContent>
          </Card>
        ) : benchmarksError ? (
          <Card className="bg-[#060B18]/60 border-red-500/20 h-60">
            <TelemetryErrorWidget title="Landscape Details Offline" message={benchmarksError} />
          </Card>
        ) : (
          <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
            <CardHeader>
              <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">
                COMPETITIVE LANDSCAPE INDEX
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader className="border-[#1F2937]/40 bg-[#030712]/40">
                  <TableRow className="border-[#1F2937]/40">
                    <TableHead className="text-slate-500 font-mono text-[10px]">BRAND NAME</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center">RANK</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center">REP SCORE</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center">SENTIMENT INDEX</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center">RISK INDEX</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center">SOV</TableHead>
                    <TableHead className="text-slate-500 font-mono text-[10px] text-center flex items-center justify-center space-x-1">
                      <span>THREAT LEVEL</span>
                      <div className="group relative cursor-help">
                        <Info className="h-3 w-3 text-slate-500 hover:text-slate-200" />
                        <div className="absolute z-50 hidden group-hover:block bg-[#030712] border border-[#1F2937] p-2.5 rounded shadow-2xl font-mono text-[8px] w-64 text-left space-y-1 right-0 top-full mt-1.5 leading-normal normal-case font-normal text-slate-400">
                          <span className="font-bold text-[#D4AF37] block mb-1">Threat Index Calculation:</span>
                          Formula: <code className="text-slate-200">SOV * 0.40 + (100 - Reputation) * 0.30 + Risk * 0.30</code>
                          <ul className="list-disc pl-3.5 space-y-0.5 mt-1">
                            <li>&ge; 75: Critical Threat</li>
                            <li>&ge; 50: High Threat</li>
                            <li>&ge; 25: Medium Threat</li>
                            <li>&lt; 25: Low Threat</li>
                          </ul>
                        </div>
                      </div>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {/* C4: rankedBrands always contains the client row even with
                      zero competitors, so `rankedBrands.length === 0` never
                      fires and a client-only "comparison" (misleadingly ranked
                      #1) rendered instead of an honest empty state. Gate on
                      actual competitor presence instead. */}
                  {normalizedBenchmarks.length > 0 ? (
                    rankedBrands.map((brand, i) => {
                      // C2: threat level is a competitor's threat to the client;
                      // it is not meaningful applied to the client's own row,
                      // and the formula is weighted toward SOV (0.40), which the
                      // client structurally dominates (clientSOV = 100 - sum of
                      // competitor SOV), so the client's own row would score as
                      // a "threat" against itself. Only compute it for competitors.
                      const threat = brand.isClient ? null : getThreatLevel(brand.sov, brand.reputation, brand.risk);
                      return (
                        <TableRow
                          key={i}
                          className={`border-[#1F2937]/40 hover:bg-[#060B18] transition-colors ${
                            brand.isClient ? "bg-[#D4AF37]/5 hover:bg-[#D4AF37]/10" : ""
                          }`}
                        >
                          <TableCell className="font-mono text-xs font-bold text-slate-200">
                            {brand.name} {brand.isClient ? "(Client)" : ""}
                          </TableCell>
                          <TableCell className={`text-center font-mono text-xs font-bold ${
                            brand.isClient ? "text-[#D4AF37]" : "text-slate-400"
                          }`}>
                            {brand.rankStr}
                          </TableCell>
                          <TableCell className="text-center font-mono text-xs font-bold text-slate-200">
                            {brand.reputation.toFixed(1)}
                          </TableCell>
                          <TableCell className="text-center font-mono text-xs text-slate-300">
                            {brand.hasEvidence ? brand.sentiment.toFixed(1) : (
                              <span className="text-slate-600">No Data</span>
                            )}
                          </TableCell>
                          <TableCell className="text-center font-mono text-xs text-slate-300">
                            {brand.risk.toFixed(1)}
                          </TableCell>
                          <TableCell className="text-center font-mono text-xs text-slate-300">
                            {brand.sov.toFixed(1)}%
                          </TableCell>
                          <TableCell className="text-center">
                            {threat ? (
                              <Badge className={`font-mono text-[8px] ${threat.class}`}>
                                {threat.label}
                              </Badge>
                            ) : (
                              <span className="text-slate-600 font-mono text-[9px]">N/A (Client)</span>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })
                  ) : (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-10">
                        <div className="flex flex-col items-center space-y-3">
                          <Compass className="h-8 w-8 text-slate-500 opacity-60" />
                          <p className="text-slate-500 font-mono text-xs">Waiting for verified competitor intelligence.</p>
                          <p className="text-slate-600 font-mono text-[9px]">Competitor benchmark data will populate when competitor entities are identified and tracked.</p>
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

      {/* EXECUTIVE ACTIVITY SUMMARY CARD */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl font-mono">
        <CardHeader className="pb-3 border-b border-[#1F2937]/40">
          <CardTitle className="text-xs uppercase tracking-wider text-slate-400 flex items-center">
            <Activity className="h-4 w-4 text-[#D4AF37] mr-2" />
            Competitive Activity
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 grid gap-4 sm:grid-cols-2 md:grid-cols-5 text-[10px]">
          <div>
            <span className="text-slate-500 block">Events Analysed:</span>
            <span className="text-slate-200 font-bold">{activitySummary.total}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Highest Impact Competitor:</span>
            <span className="text-slate-200 font-bold">{activitySummary.highestImpact}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Most Mentioned Competitor:</span>
            <span className="text-slate-200 font-bold">{activitySummary.mostMentioned}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Latest Competitor Event:</span>
            <span className="text-slate-200 font-bold">{activitySummary.latestEvent}</span>
          </div>
          <div>
            <span className="text-slate-500 block">Most Active Topic:</span>
            <span className="text-slate-200 font-bold">{activitySummary.activeTopic}</span>
          </div>
        </CardContent>
      </Card>

      {/* COMPETITIVE INTELLIGENCE REGISTER */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
        <CardHeader>
          <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <div className="flex items-center">
              <Search className="h-4 w-4 text-[#38BDF8] mr-2" />
              COMPETITIVE INTELLIGENCE REGISTER
            </div>
            <Badge className="bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30 font-mono text-[9px]">
              {competitorEvents.length} Events
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader className="border-[#1F2937]/40 bg-[#030712]/40">
              <TableRow className="border-[#1F2937]/40">
                <TableHead className="text-slate-500 font-mono text-[10px]">COMPETITOR</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px]">EVENT HEADLINE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">BUSINESS TOPIC</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">REPUTATION IMPACT</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">RISK SCORE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px]">SOURCE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px]">PUBLISHED DATE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-right">ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {competitorEvents.map((doc, idx) => (
                <TableRow key={doc.id} className="border-[#1F2937]/40 hover:bg-[#060B18] transition-colors cursor-pointer" onClick={() => setSelectedDocId(doc.id)}>
                  <TableCell className="font-mono text-xs text-slate-200 font-bold">{doc.matchedCompetitor}</TableCell>
                  <TableCell className="font-mono text-xs text-slate-300 max-w-[280px] truncate">{doc.title}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className="border-[#D4AF37]/30 text-[#D4AF37] font-mono text-[9px] bg-[#D4AF37]/5">
                      {doc.topic}
                    </Badge>
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
                  <TableCell className="font-mono text-xs text-slate-400 truncate max-w-[100px]">{doc.source}</TableCell>
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
              {competitorEvents.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-10 text-slate-500 font-mono text-xs">
                    No competitor events recorded.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Risk Details Drawer (Slide-Over Panel) */}
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
                    <span className="bg-[#030712] border border-[#1F2937]/65 px-2 py-0.5 rounded text-slate-400">Matched Brand: {selectedDoc.matchedCompetitor}</span>
                  </div>
                </div>

                {/* Risk score calculation breakdown */}
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
                      <span className="text-slate-500">Sentiment Polarity (Multiplier):</span>
                      <span className="text-slate-300">{selectedDoc.sentiment?.toFixed(2) || "0.00"}</span>
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

                {/* Detected Entities */}
                <div className="space-y-2">
                  <span className="text-[10px] text-slate-500 uppercase font-bold">Extracted Named Entities</span>
                  <div className="flex flex-wrap gap-2">
                    {selectedDoc.extracted_entities && selectedDoc.extracted_entities.length > 0 ? (
                      selectedDoc.extracted_entities.map((ent: any, idx: number) => (
                        <Badge key={idx} variant="outline" className="border-blue-500/30 text-blue-400 text-[9px] bg-blue-500/5">
                          {ent.name} ({ent.entity_type})
                        </Badge>
                      ))
                    ) : (
                      <span className="text-[10px] text-slate-500">No matching corporate entities identified.</span>
                    )}
                  </div>
                </div>

              </div>

              {/* Drawer Footer */}
              <div className="p-4 border-t border-[#1F2937]/80 bg-[#030712]/50 flex justify-end space-x-3">
                {selectedDoc.url && (
                  <a 
                    href={selectedDoc.url} 
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
