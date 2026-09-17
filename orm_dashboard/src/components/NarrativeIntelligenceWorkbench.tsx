import React, { useState, useMemo, useEffect } from "react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { 
  Search, ShieldAlert, Sparkles, TrendingUp, Calendar,
  Users, Layers, ExternalLink, RefreshCw, BarChart2, CheckCircle2, AlertTriangle, Link2
} from "lucide-react";
import { fetchDocumentDetails } from "@/lib/api";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";
import { getNarrativeDocuments, getMissingSupportingDocumentIds, fetchMissingNarrativeDocuments } from "@/utils/narrativeEvidence";
import { findRelatedNarrativesForAll } from "@/utils/narrativeSimilarity";
import { isValidOriginalArticleUrl } from "@/utils/urlValidation";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassPill, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { isPlaceholderTitle, PreviewUnavailableLabel, PLACEHOLDER_ROW_CLASS } from "@/components/ui/PreviewUnavailable";

interface NarrativeIntelligenceWorkbenchProps {
  documents: any[];
  executives: any[];
  narratives: any[];
  clientName: string;
  clientId?: string;
  onSelectDocument: (doc: any) => void;
}

export function NarrativeIntelligenceWorkbench({
  documents = [],
  executives = [],
  narratives = [],
  clientName,
  clientId,
  onSelectDocument
}: NarrativeIntelligenceWorkbenchProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const accent2 = isDark ? "#7B2CBF" : "#8B5CF6";
  // State for selected narrative -- auto-selected below once real data
  // arrives (see the effect after narrativeList/activeNarrative), not here.
  const [selectedNarrativeId, setSelectedNarrativeId] = useState<string | null>(null);

  // Filters & Sorting state
  const [searchTerm, setSearchTerm] = useState("");
  const [sortBy, setSortBy] = useState<"risk" | "mentions" | "trend" | "recent">("risk");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [docUrls, setDocUrls] = useState<Record<string, string | null>>({});

  // Bounded render window for the Narrative Registry list, same fix
  // pattern already used for the Intelligence Stream feed (FeedTab.tsx's
  // feedRenderCount): a large client (e.g. Tesla's 2,416 narratives) was
  // mounting a fully-expanded detail block for every single narrative at
  // once (~97,000 DOM nodes measured live), which froze the browser tab on
  // scroll. The full narrative list is still fetched and searched/sorted
  // exactly as before -- only how many of the matching results get mounted
  // to the DOM at once is bounded here.
  const NARRATIVE_PAGE_SIZE = 25;
  const [narrativeRenderCount, setNarrativeRenderCount] = useState(NARRATIVE_PAGE_SIZE);

  // Reset back to the first page whenever the result set a viewer is
  // looking at changes underneath them -- a new search/sort/status filter,
  // or switching to a different client's narratives entirely.
  useEffect(() => {
    setNarrativeRenderCount(NARRATIVE_PAGE_SIZE);
  }, [searchTerm, sortBy, statusFilter, clientId]);

  // Fallback for narrative evidence documents that have aged out of the
  // main 500-most-recent-document window (see the lazy fetch effect below,
  // keyed off activeNarrative) -- keyed by doc id so results accumulate
  // across every narrative visited this session instead of being
  // overwritten. Since these ids are, by construction, only ever ones
  // missing from `documents`, concatenating the two below can't double-count.
  const [extraDocs, setExtraDocs] = useState<Record<string, any>>({});
  const [fetchingMissingDocs, setFetchingMissingDocs] = useState(false);

  const documentsWithFallback = useMemo(() => {
    const extra = Object.values(extraDocs);
    return extra.length > 0 ? [...documents, ...extra] : documents;
  }, [documents, extraDocs]);

  // Derived narrative stats & list mapping
  const narrativeList = useMemo(() => {
    const items = narratives.map(n => {
      // Real cluster membership: evidence_metadata.supporting_documents is
      // the exact document ID list narrative_engine.py's clustering (3-day
      // window, title-Jaccard, entity overlap, source-diversity gate)
      // produced for this narrative -- not a name/topic-substring re-scan
      // over the whole per-client feed. documentsWithFallback folds in any
      // evidence documents fetched on-demand because they'd aged out of
      // the main window (see the effect below) -- this recomputes for
      // every narrative each time that fallback set grows, which is cheap
      // (a handful of ids at most) and keeps this the single place
      // rawDocs/docsCount are derived from.
      const docs = getNarrativeDocuments(n, documentsWithFallback);

      // Find affected executives
      const meta = n.evidence_metadata || {};
      const supportEntities = meta.supporting_entities || [];
      const affectedExecs = executives
        .filter(e => supportEntities.includes(e.entity_id))
        .map(e => e.name);

      // confidence_score is stored 0-1 (narrative_engine.py's final_score);
      // scale to a percentage like ExecutivesTab/NarrativesTab do. Fall back
      // to null (rendered "Not Available") when the backend has no score,
      // not a fabricated always-≥80% formula (FINDINGS.md #33).
      const confidence = typeof n.confidence_score === "number" ? Math.round(n.confidence_score * 100)
        : typeof n.confidence === "number" ? n.confidence
        : null;

      // Status tier
      let status = "Emerging";
      if (n.risk >= 75 || n.mentions > 30) {
        status = "Critical";
      } else if (n.risk < 40 && n.trend < 0) {
        status = "Mitigated";
      } else if (n.mentions > 10) {
        status = "Active";
      }

      // Latest timestamp
      const timestamps = docs
        .map(d => d.timestamp ? new Date(d.timestamp).getTime() : 0)
        .filter(t => t > 0);
      const lastDetectedTs = timestamps.length > 0 ? Math.max(...timestamps) : null;
      const lastDetected = lastDetectedTs !== null
        ? new Date(lastDetectedTs).toLocaleDateString("en-US", { month: "short", day: "numeric" })
        : "Recent";

      return {
        ...n,
        docsCount: docs.length,
        affectedExecs,
        confidence,
        status,
        lastDetected,
        lastDetectedTs,
        rawDocs: docs
      };
    });

    // Near-duplicate-story hint: same title-Jaccard + day-window recipe
    // narrative_engine.py's own document clustering uses, applied one level
    // up across narrative names instead of document titles. Display-only --
    // it never merges narratives or changes clustering. Computed once for
    // every item via the batch helper (each name tokenized once, not once
    // per pairwise comparison) rather than in a per-item loop.
    const relatedById = findRelatedNarrativesForAll(items, clientName);
    return items.map(item => ({
      ...item,
      relatedNarratives: (relatedById.get(item.id) || []).map(r => r.name)
    }));
  }, [narratives, documentsWithFallback, executives, clientName]);

  const activeNarrative = useMemo(() => {
    if (!selectedNarrativeId) return null;
    return narrativeList.find(n => n.id === selectedNarrativeId) || null;
  }, [selectedNarrativeId, narrativeList]);

  // Auto-select once real data is available. Keyed on activeNarrative
  // (not selectedNarrativeId) so this also self-heals a stale selection
  // left over from a previous client whose narratives no longer match --
  // not just the initial-load case (FINDINGS.md #32).
  useEffect(() => {
    if (!activeNarrative && narrativeList.length > 0) {
      setSelectedNarrativeId(narrativeList[0].id);
    }
  }, [activeNarrative, narrativeList]);

  // Lazy, targeted fallback: only runs for the narrative actually being
  // viewed (not eagerly for all of them), and only fetches the specific
  // supporting_documents ids this narrative is missing from `documents` --
  // e.g. because they've aged out of the 500-most-recent-document window.
  // Skips entirely (no request at all) when nothing is missing, which is
  // the common case for a narrative whose evidence is still recent.
  useEffect(() => {
    if (!activeNarrative || !clientId) return;
    const missingIds = getMissingSupportingDocumentIds(activeNarrative, documents);
    const stillMissing = missingIds.filter(id => !(id in extraDocs));
    if (stillMissing.length === 0) return;

    let cancelled = false;
    setFetchingMissingDocs(true);
    fetchMissingNarrativeDocuments(clientId, activeNarrative, documents)
      .then(fetched => {
        if (cancelled || fetched.length === 0) return;
        setExtraDocs(prev => {
          const next = { ...prev };
          for (const doc of fetched) next[String(doc.id)] = doc;
          return next;
        });
      })
      .finally(() => {
        if (!cancelled) setFetchingMissingDocs(false);
      });

    return () => { cancelled = true; };
  }, [activeNarrative, clientId]);

  useEffect(() => {
    if (!activeNarrative || !activeNarrative.rawDocs || !clientId) return;
    activeNarrative.rawDocs.forEach((doc: any) => {
      fetchDocumentDetails(clientId, doc.id)
        .then(details => {
          setDocUrls(prev => {
            if (prev[doc.id] === details?.url) return prev;
            return { ...prev, [doc.id]: details?.url || null };
          });
        })
        .catch(() => {
          setDocUrls(prev => {
            if (prev[doc.id] === null) return prev;
            return { ...prev, [doc.id]: null };
          });
        });
    });
  }, [activeNarrative, clientId]);

  // Filtered & Sorted list
  const processedNarratives = useMemo(() => {
    let result = [...narrativeList];

    // Search query
    if (searchTerm.trim() !== "") {
      const q = searchTerm.toLowerCase();
      result = result.filter(n => 
        n.name.toLowerCase().includes(q) || 
        (n.description && n.description.toLowerCase().includes(q))
      );
    }

    // Status filter
    if (statusFilter !== "all") {
      result = result.filter(n => n.status.toLowerCase() === statusFilter.toLowerCase());
    }

    // Sorting
    result.sort((a, b) => {
      if (sortBy === "risk") return (b.risk || 0) - (a.risk || 0);
      if (sortBy === "mentions") return (b.mentions || 0) - (a.mentions || 0);
      if (sortBy === "trend") return (b.trend || 0) - (a.trend || 0);
      return (b.docsCount || 0) - (a.docsCount || 0);
    });

    return result;
  }, [narrativeList, searchTerm, sortBy, statusFilter]);

  // Select narrative callback helper
  const handleSelectNarrative = (id: string) => {
    setSelectedNarrativeId(id);
  };

  return (
    <div className={`grid grid-cols-12 gap-6 w-full ${bodyText(theme)}`}>

      {/* LEFT: Narrative Register (40% space) */}
      <Card className={`col-span-12 lg:col-span-5 ${glassCard(theme)} overflow-hidden flex flex-col h-[750px]`} style={{ borderLeftWidth: 2, borderLeftColor: `${accent}66` }}>
        <div className={SPECULAR_LINE} />
        <CardHeader className={`pb-3 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
          <div className="flex justify-between items-center mb-3">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 ${mutedText(theme)}`}>
              <Layers className="h-3.5 w-3.5" /> Narrative Registry
            </CardTitle>
            <Badge className={glassPill(theme)} style={{ color: accent }}>
              {processedNarratives.length} Classified
            </Badge>
          </div>

          <div className="grid grid-cols-12 gap-2 mt-2">
            <div className="col-span-6 relative">
              <Search className={`absolute left-2.5 top-2 h-3.5 w-3.5 ${mutedText(theme)}`} />
              <input
                type="text"
                placeholder="Query database..."
                className={`w-full rounded px-2 py-1.5 pl-8 text-[11px] font-mono focus:outline-none ${bodyText(theme)} ${isDark ? "bg-black/40 border border-white/[0.12] placeholder-zinc-600 focus:border-[#00F5D4]/50" : "bg-white/60 border border-black/[0.08] placeholder-zinc-400 focus:border-[#3B82F6]/50"}`}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>

            <div className="col-span-3">
              <select
                className={`w-full rounded px-2 py-1.5 text-[11px] font-mono focus:outline-none cursor-pointer ${bodyText(theme)} ${isDark ? "bg-black/40 border border-white/[0.12] focus:border-[#00F5D4]/50" : "bg-white/60 border border-black/[0.08] focus:border-[#3B82F6]/50"}`}
                value={sortBy}
                onChange={(e: any) => setSortBy(e.target.value)}
              >
                <option value="risk">High Risk</option>
                <option value="mentions">Volume</option>
                <option value="trend">Velocity</option>
              </select>
            </div>

            <div className="col-span-3">
              <select
                className={`w-full rounded px-2 py-1.5 text-[11px] font-mono focus:outline-none cursor-pointer ${bodyText(theme)} ${isDark ? "bg-black/40 border border-white/[0.12] focus:border-[#00F5D4]/50" : "bg-white/60 border border-black/[0.08] focus:border-[#3B82F6]/50"}`}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="all">All Tiers</option>
                <option value="critical">Critical</option>
                <option value="active">Active</option>
                <option value="emerging">Emerging</option>
                <option value="mitigated">Mitigated</option>
              </select>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-3 overflow-y-auto flex-1 space-y-2.5 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
          {processedNarratives.length > 0 ? (
            <>
            {processedNarratives.slice(0, narrativeRenderCount).map((n) => {
              const isSelected = selectedNarrativeId === n.id;
              const riskTextColor = n.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-500" : n.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-amber-500" : "";
              const statusBadgeColor = n.status === "Critical" ? "bg-red-500/10 text-red-500 border border-red-500/20" : n.status === "Active" ? "bg-amber-500/10 text-amber-500 border border-amber-500/20" : n.status === "Mitigated" ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20" : `${mutedText(theme)} ${isDark ? "bg-white/[0.04] border border-white/[0.12]" : "bg-black/[0.03] border border-black/[0.08]"}`;

              return (
                <div
                  key={n.id}
                  onClick={() => handleSelectNarrative(n.id)}
                  className={`border rounded-lg p-3 cursor-pointer transition-all duration-200 ${
                    isSelected
                      ? isDark ? "bg-white/[0.06] border-[#00F5D4]/60" : "bg-black/[0.03] border-[#3B82F6]/60"
                      : isDark ? "bg-black/20 border-white/[0.08] hover:border-white/[0.2] hover:bg-black/30" : "bg-black/[0.02] border-black/[0.06] hover:border-black/[0.15] hover:bg-black/[0.04]"
                  }`}
                >
                  <div className="flex justify-between items-start gap-2 mb-1.5">
                    <span className={`font-bold text-xs transition-colors duration-150 ${bodyText(theme)}`}>
                      {n.name}
                    </span>
                    <Badge variant="outline" className={`font-mono text-[9px] px-1.5 py-0 ${statusBadgeColor}`}>
                      {n.status}
                    </Badge>
                  </div>

                  <p className={`text-[10px] leading-normal line-clamp-2 mb-2 font-mono ${mutedText(theme)}`}>
                    {/* xoop_ui_clarity_review.md: this always showed the same
                        boilerplate line for every narrative, since `n.description`
                        is never actually populated by the backend. The real
                        per-narrative AI summary (same one the drill-through
                        drawer reads) lives at evidence_metadata.rca.problem_statement,
                        but narrative_engine.py only generates an RCA for
                        risk-worthy narratives, so a genuine narrative-specific
                        fallback is still needed for the rest. */}
                    {n.evidence_metadata?.rca?.problem_statement || n.description || "No AI-generated summary available for this narrative yet."}
                  </p>

                  <div className={`grid grid-cols-4 gap-2 pt-2 border-t text-[9px] font-mono ${mutedText(theme)} ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                    <div>
                      <span className={`block text-[8px] uppercase ${mutedText(theme)}`}>Reputation Impact</span>
                      <span className={`font-bold ${riskTextColor}`} style={riskTextColor ? undefined : { color: accent }}>{Math.round(n.risk)} pts</span>
                    </div>
                    <div>
                      <span className={`block text-[8px] uppercase ${mutedText(theme)}`}>How Fast It&apos;s Spreading</span>
                      {/* Plain-language pace instead of a bare velocity % --
                          same 50%-move bar the platform already uses
                          elsewhere as its "genuinely significant swing"
                          threshold (narrative_engine.py's
                          NARRATIVE_REQUIRE_RISING_TREND / TrendDetector's
                          24h-vs-7d gate), not an invented cutoff. */}
                      <span className={`font-bold ${n.trend >= 50 ? "text-red-500" : n.trend <= -50 ? "text-emerald-500" : bodyText(theme)}`}>
                        {n.trend >= 50 ? "Accelerating" : n.trend <= -50 ? "Slowing" : "Steady"}
                      </span>
                    </div>
                    <div>
                      <span className={`block text-[8px] uppercase ${mutedText(theme)}`}>Coverage So Far</span>
                      <span className={`font-bold ${bodyText(theme)}`}>{n.mentions} article{n.mentions === 1 ? "" : "s"}</span>
                    </div>
                    <div className="text-right">
                      <span className={`block text-[8px] uppercase ${mutedText(theme)}`}>How Sure We Are This Is Real</span>
                      {/* Qualitative instead of a raw "31%" next to a
                          serious-sounding narrative title -- same
                          confidence value, just not shown as a bare number
                          (ui_redesign_plan.md #7). */}
                      <span className="font-bold" style={{ color: accent }}>
                        {n.confidence === null ? "Not enough data yet" : n.confidence >= 60 ? "High" : n.confidence >= 35 ? "Moderate" : "Low"}
                      </span>
                    </div>
                  </div>

                  {n.affectedExecs.length > 0 && (
                    <div className={`mt-2 pt-1.5 border-t border-dashed flex items-center gap-1.5 text-[8.5px] font-mono ${mutedText(theme)} ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                      <Users className="h-3 w-3" style={{ color: accent }} />
                      <span className={`font-bold uppercase ${mutedText(theme)}`}>TARGETS:</span>
                      <span className="truncate max-w-[220px]">{n.affectedExecs.join(", ")}</span>
                    </div>
                  )}

                  {n.relatedNarratives.length > 0 && (
                    <div className={`mt-2 pt-1.5 border-t border-dashed flex items-start gap-1.5 text-[8.5px] font-mono ${mutedText(theme)} ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                      <Link2 className="h-3 w-3 mt-0.5 shrink-0" style={{ color: accent2 }} />
                      <span>
                        <span className={`font-bold uppercase ${mutedText(theme)}`}>Related to:</span>{" "}
                        <span className="italic">{n.relatedNarratives.join(", ")}</span> — may be the same underlying story.
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
            {processedNarratives.length > narrativeRenderCount && (
              <button
                type="button"
                onClick={() => setNarrativeRenderCount((c) => c + NARRATIVE_PAGE_SIZE)}
                className={`w-full text-center text-[10px] font-mono uppercase tracking-wider py-2.5 rounded-lg border ${isDark ? "border-white/[0.08] text-zinc-400 hover:bg-white/[0.03]" : "border-black/[0.06] text-zinc-600 hover:bg-black/[0.02]"}`}
              >
                Load {Math.min(NARRATIVE_PAGE_SIZE, processedNarratives.length - narrativeRenderCount)} more ({narrativeRenderCount} of {processedNarratives.length})
              </button>
            )}
            </>
          ) : (
            <div className={`flex flex-col items-center justify-center h-full font-mono text-xs py-10 ${mutedText(theme)}`}>
              No matching narrative vectors found.
            </div>
          )}
        </CardContent>
      </Card>

      {/* CENTER: AI Analysis Details (35% space) */}
      <Card className={`col-span-12 lg:col-span-4 ${glassCard(theme)} overflow-hidden flex flex-col h-[750px]`} style={{ borderLeftWidth: 2, borderLeftColor: `${accent}66` }}>
        <div className={SPECULAR_LINE} />
        <CardHeader className={`pb-3 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
          <div className="flex justify-between items-center">
            <CardTitle className="text-xs font-mono uppercase tracking-wider flex items-center gap-1.5" style={{ color: accent }}>
              <Sparkles className="h-3.5 w-3.5" style={{ color: accent }} /> AI Analysis details
            </CardTitle>
            {activeNarrative && (
              <Badge className="bg-purple-500/10 text-purple-400 border border-purple-500/20 font-mono text-[9px]">
                Classification: {activeNarrative.type || "Reputation"}
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="p-4 overflow-y-auto flex-1 space-y-4 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent font-mono text-xs">
          {activeNarrative ? (
            <>
              {/* Core Header info */}
              <div>
                <h3 className={`text-sm font-bold uppercase tracking-tight ${bodyText(theme)}`}>{activeNarrative.name}</h3>
                <span className={`text-[9px] block mt-1 ${mutedText(theme)}`}>LAST AUDITED: {activeNarrative.lastDetected || "TODAY"}</span>
              </div>

              {/* AI generated Narrative Executive Summary */}
              <div className="space-y-1.5">
                <span className={`text-[9.5px] font-bold uppercase tracking-wider block border-b pb-1 ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`} style={{ color: accent }}>AI Executive Summary</span>
                {activeNarrative.summary_text ? (
                  <p className={`text-[10px] leading-relaxed font-mono ${bodyText(theme)}`}>
                    {activeNarrative.summary_text}
                  </p>
                ) : (
                  <>
                    <p className={`text-[10px] leading-relaxed font-mono ${bodyText(theme)}`}>
                      This reputation coordinate outlines media anomalies targeting public profiles connected to {clientName}. Public traction focuses on {activeNarrative.name.toLowerCase()} with an index intensity rating of {Math.round(activeNarrative.risk)} pts.
                    </p>
                    <p className={`text-[10px] leading-relaxed font-mono mt-1 border-t border-dashed pt-1.5 ${mutedText(theme)} ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                      {activeNarrative.evidence_metadata?.rca?.problem_statement || activeNarrative.description || "No AI-generated summary available for this narrative yet."}
                    </p>
                  </>
                )}
              </div>

              {/* Metrics Breakdown Grid */}
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div className={`rounded-lg p-2 text-center border ${isDark ? "bg-black/20 border-white/[0.08]" : "bg-black/[0.02] border-black/[0.06]"}`}>
                  <span className={`text-[8px] block uppercase font-bold ${mutedText(theme)}`}>Risk Index</span>
                  <span className="text-sm font-bold block mt-0.5" style={{ color: activeNarrative.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "#EF4444" : activeNarrative.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "#F59E0B" : accent }}>{Math.round(activeNarrative.risk)} pts</span>
                  <span className={`text-[8px] block mt-0.5 ${mutedText(theme)}`}>{activeNarrative.risk >= 60 ? "HIGH PROFILE" : "MONITORED"}</span>
                </div>
                <div className={`rounded-lg p-2 text-center border ${isDark ? "bg-black/20 border-white/[0.08]" : "bg-black/[0.02] border-black/[0.06]"}`}>
                  <span className={`text-[8px] block uppercase font-bold ${mutedText(theme)}`}>Velocity Index</span>
                  <span className={`text-sm font-bold block mt-0.5 ${activeNarrative.trend >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                    {activeNarrative.trend >= 0 ? "+" : ""}{activeNarrative.trend?.toFixed(1)}%
                  </span>
                  <span className={`text-[8px] block mt-0.5 ${mutedText(theme)}`}>{activeNarrative.trend >= 15 ? "EXPANDING" : "STABLE"}</span>
                </div>
              </div>

              {/* Entity relationships */}
              <div className="space-y-2">
                <span className={`text-[9.5px] font-bold uppercase tracking-wider block border-b pb-1 ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`} style={{ color: accent }}>Entity Map</span>
                <div className="space-y-1.5 text-[9.5px]">
                  <div className="flex justify-between">
                    <span className={mutedText(theme)}>Primary Targets:</span>
                    <span className={`font-bold ${bodyText(theme)}`}>{activeNarrative.affectedExecs?.join(", ") || "Corporate Management"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className={mutedText(theme)}>Connected Sources:</span>
                    <span className={bodyText(theme)}>{activeNarrative.docsCount} distinct documents</span>
                  </div>
                  <div className="flex justify-between">
                    <span className={mutedText(theme)}>Reputation Velocity:</span>
                    <span className={`font-bold ${activeNarrative.sentiment >= 0.2 ? "text-emerald-500" : activeNarrative.sentiment <= -0.2 ? "text-red-500" : "text-amber-500"}`}>
                      {activeNarrative.sentiment !== undefined ? activeNarrative.sentiment.toFixed(2) : "0.00"} sentiment
                    </span>
                  </div>
                </div>
              </div>

              {/* Recommended Response Action Plan */}
              <div className="space-y-2">
                <span className={`text-[9.5px] font-bold uppercase tracking-wider block border-b pb-1 ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`} style={{ color: accent }}>Action Recommendations</span>
                <div className={`rounded-lg p-2.5 text-[10px] space-y-1.5 border ${bodyText(theme)}`} style={{ backgroundColor: `${accent}1A`, borderColor: `${accent}40` }}>
                  <div className="flex gap-1.5 items-start">
                    <CheckCircle2 className="h-3.5 w-3.5 mt-0.5 shrink-0" style={{ color: accent }} />
                    <span>
                      {activeNarrative.risk >= 70
                        ? "Execute press counter-communication and alert executive communications team."
                        : "Monitor timeline activity and set alert pipelines for volume spikes above 15%."}
                    </span>
                  </div>
                  <div className="flex gap-1.5 items-start">
                    <CheckCircle2 className="h-3.5 w-3.5 mt-0.5 shrink-0" style={{ color: accent }} />
                    <span>Audit supporting sources checklist to scan for organized narrative distribution.</span>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className={`flex flex-col items-center justify-center h-full font-mono text-xs py-20 text-center ${mutedText(theme)}`}>
              <BarChart2 className={`h-8 w-8 mb-2 ${mutedText(theme)}`} />
              Select a narrative from the registry to view detailed intelligence analysis.
            </div>
          )}
        </CardContent>
      </Card>

      {/* RIGHT: Evidence & Documents (25% space) */}
      <Card className={`col-span-12 lg:col-span-3 ${glassCard(theme)} overflow-hidden flex flex-col h-[750px]`} style={{ borderLeftWidth: 2, borderLeftColor: "rgba(16,185,129,0.4)" }}>
        <div className={SPECULAR_LINE} />
        <CardHeader className={`pb-3 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
          <div className="flex justify-between items-center">
            <CardTitle className="text-xs font-mono uppercase tracking-wider flex items-center gap-1.5" style={{ color: accent }}>
              <Calendar className="h-3.5 w-3.5" /> Source Evidence
            </CardTitle>
            <Badge className={glassPill(theme) + " text-emerald-500"}>
              {activeNarrative ? activeNarrative.docsCount : 0} Sources
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="p-3 overflow-y-auto flex-1 space-y-2 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
          {activeNarrative ? (
            activeNarrative.rawDocs && activeNarrative.rawDocs.length > 0 ? (
              activeNarrative.rawDocs.map((doc: any) => {
                const docRiskColorClass = doc.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-500 bg-red-500/10" : doc.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-amber-500 bg-amber-500/10" : "";
                const formattedDate = doc.timestamp
                  ? new Date(doc.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" })
                  : "Unknown";
                const isPlaceholder = isPlaceholderTitle(doc.title, doc.source);

                // Infer Source Type from the source name
                let typeLabel = "news";
                if (doc.source) {
                  const s = doc.source.toLowerCase();
                  if (s.includes("reddit")) typeLabel = "reddit";
                  else if (s.includes("youtube")) typeLabel = "youtube";
                  else if (s.includes("blog")) typeLabel = "blog";
                  else if (s.includes("forum")) typeLabel = "forum";
                }

                return (
                  <div
                    key={doc.id}
                    onClick={() => onSelectDocument(doc)}
                    className={`rounded-lg p-2.5 transition-all duration-150 cursor-pointer space-y-2 group relative border ${isDark ? "bg-black/20 border-white/[0.08] hover:border-emerald-500/40 hover:bg-black/30" : "bg-black/[0.02] border-black/[0.06] hover:border-emerald-500/40 hover:bg-black/[0.04]"} ${isPlaceholder ? PLACEHOLDER_ROW_CLASS : ""}`}
                  >
                    <div className="flex justify-between items-start gap-2">
                      <span className={`font-bold text-[10px] transition-colors duration-150 line-clamp-2 leading-tight ${bodyText(theme)}`}>
                        {isPlaceholder ? <PreviewUnavailableLabel /> : doc.title}
                      </span>
                    </div>

                    {/* Metadata fields requested by user */}
                    <div className={`grid grid-cols-2 gap-y-1 text-[8px] font-mono border-t pt-1.5 ${mutedText(theme)} ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                      <div>
                        <span className={mutedText(theme)}>SOURCE:</span> <span className={bodyText(theme)}>{doc.source || "RSS Feed"}</span>
                      </div>
                      <div>
                        <span className={mutedText(theme)}>TYPE:</span> <span className={`capitalize ${bodyText(theme)}`}>{typeLabel}</span>
                      </div>
                      <div>
                        <span className={mutedText(theme)}>DATE:</span> <span className={bodyText(theme)}>{formattedDate}</span>
                      </div>
                      <div>
                        <span className={mutedText(theme)}>SENTIMENT:</span> <span className={`font-bold ${doc.sentiment >= 0.2 ? "text-emerald-500" : doc.sentiment <= -0.2 ? "text-red-500" : "text-amber-500"}`}>{doc.sentiment?.toFixed(2) || "0.00"}</span>
                      </div>
                      <div>
                        <span className={mutedText(theme)}>RISK SCORE:</span> <span className={`font-bold ${docRiskColorClass || bodyText(theme)}`}>{Math.round(doc.risk || 0)}</span>
                      </div>
                    </div>

                    {/* Document control actions - Single Button Requested */}
                    <div className={`flex gap-1.5 pt-1.5 border-t border-dashed w-full ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                      {docUrls[doc.id] !== undefined && isValidOriginalArticleUrl(docUrls[doc.id]) ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={(e) => {
                            e.stopPropagation();
                            const url = docUrls[doc.id];
                            if (url) {
                              window.open(url, "_blank", "noopener,noreferrer");
                            }
                          }}
                          className={`h-5 px-1.5 text-[8.5px] font-mono flex items-center gap-1 w-full justify-center border ${isDark ? "bg-black/40 border-white/[0.12] hover:bg-white/[0.08]" : "bg-white/60 border-black/[0.08] hover:bg-black/[0.04]"}`}
                          style={{ color: accent }}
                        >
                          <ExternalLink className="h-2 w-2" /> Open Original Article
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled
                          className={`h-5 px-1.5 text-[8.5px] font-mono flex items-center gap-1 w-full justify-center cursor-not-allowed opacity-50 border ${mutedText(theme)} ${isDark ? "bg-black/40 border-white/[0.12]" : "bg-white/60 border-black/[0.08]"}`}
                        >
                          Original article unavailable
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })
            ) : fetchingMissingDocs ? (
              <div className={`flex flex-col items-center justify-center h-full font-mono text-xs py-20 text-center ${mutedText(theme)}`}>
                <RefreshCw className={`h-5 w-5 mb-1 animate-spin ${mutedText(theme)}`} />
                Loading additional sources...
              </div>
            ) : (
              <div className={`flex flex-col items-center justify-center h-full font-mono text-xs py-20 text-center ${mutedText(theme)}`}>
                <AlertTriangle className={`h-5 w-5 mb-1 ${mutedText(theme)}`} />
                No supporting documents found.
              </div>
            )
          ) : (
            <div className={`flex flex-col items-center justify-center h-full font-mono text-xs py-20 text-center ${mutedText(theme)}`}>
              No narrative selected.
            </div>
          )}
        </CardContent>
      </Card>
      
    </div>
  );
}
