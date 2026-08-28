import React, { useState, useMemo, useEffect } from "react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { 
  Search, ShieldAlert, Sparkles, TrendingUp, Calendar, 
  Users, Layers, ExternalLink, RefreshCw, BarChart2, CheckCircle2, AlertTriangle
} from "lucide-react";
import { fetchDocumentDetails } from "@/lib/api";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";
import { isValidOriginalArticleUrl } from "@/utils/urlValidation";

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
  // State for selected narrative -- auto-selected below once real data
  // arrives (see the effect after narrativeList/activeNarrative), not here.
  const [selectedNarrativeId, setSelectedNarrativeId] = useState<string | null>(null);

  // Filters & Sorting state
  const [searchTerm, setSearchTerm] = useState("");
  const [sortBy, setSortBy] = useState<"risk" | "mentions" | "trend" | "recent">("risk");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [docUrls, setDocUrls] = useState<Record<string, string | null>>({});

  // Derived narrative stats & list mapping
  const narrativeList = useMemo(() => {
    return narratives.map(n => {
      // Find matching documents
      const docs = documents.filter(d => 
        (d.narrative && d.narrative.toLowerCase() === n.name.toLowerCase()) ||
        (d.topic && n.name.toLowerCase().includes(d.topic.toLowerCase()))
      );

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
      const lastDetected = timestamps.length > 0 
        ? new Date(Math.max(...timestamps)).toLocaleDateString("en-US", { month: "short", day: "numeric" })
        : "Recent";

      return {
        ...n,
        docsCount: docs.length,
        affectedExecs,
        confidence,
        status,
        lastDetected,
        rawDocs: docs
      };
    });
  }, [narratives, documents, executives]);

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
    <div className="grid grid-cols-12 gap-6 w-full text-slate-200">
      
      {/* LEFT: Narrative Register (40% space) */}
      <Card className="col-span-12 lg:col-span-5 bg-[#050B18]/85 border-[#1F2937]/75 shadow-2xl backdrop-blur-md rounded-xl overflow-hidden flex flex-col h-[750px] relative border-l-2 border-l-sky-500/40">
        <CardHeader className="pb-3 border-b border-[#1F2937]/40 bg-[#030712]/50 p-4">
          <div className="flex justify-between items-center mb-3">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-[#D4AF37] flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5" /> Narrative Registry
            </CardTitle>
            <Badge className="bg-[#030712] text-sky-400 border border-[#1F2937] font-mono text-[9px]">
              {processedNarratives.length} Classified
            </Badge>
          </div>
          
          <div className="grid grid-cols-12 gap-2 mt-2">
            <div className="col-span-6 relative">
              <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="Query database..."
                className="w-full bg-[#030712]/80 border border-[#1F2937] text-slate-200 placeholder-slate-500 rounded px-2 py-1.5 pl-8 text-[11px] font-mono focus:outline-none focus:border-[#D4AF37]/50"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            
            <div className="col-span-3">
              <select
                className="w-full bg-[#030712]/80 border border-[#1F2937] text-slate-200 rounded px-2 py-1.5 text-[11px] font-mono focus:outline-none focus:border-[#D4AF37]/50 cursor-pointer"
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
                className="w-full bg-[#030712]/80 border border-[#1F2937] text-slate-200 rounded px-2 py-1.5 text-[11px] font-mono focus:outline-none focus:border-[#D4AF37]/50 cursor-pointer"
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
            processedNarratives.map((n) => {
              const isSelected = selectedNarrativeId === n.id;
              const riskColor = n.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-400 border-red-950/40 bg-red-950/20" : n.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-amber-400 border-amber-950/40 bg-amber-950/20" : "text-sky-400 border-sky-950/40 bg-sky-950/20";
              const trendSign = n.trend >= 0 ? "+" : "";
              const statusBadgeColor = n.status === "Critical" ? "bg-red-950/40 text-red-400 border border-red-800/40" : n.status === "Active" ? "bg-amber-950/40 text-amber-400 border border-amber-800/40" : n.status === "Mitigated" ? "bg-emerald-950/40 text-emerald-400 border border-emerald-800/40" : "bg-sky-950/40 text-sky-400 border border-sky-800/40";

              return (
                <div
                  key={n.id}
                  onClick={() => handleSelectNarrative(n.id)}
                  className={`border rounded-lg p-3 cursor-pointer transition-all duration-200 ${
                    isSelected
                      ? "bg-[#060C1E] border-sky-500/60 shadow-[0_0_12px_rgba(56,189,248,0.15)]"
                      : "bg-[#030712]/40 border-[#1F2937]/60 hover:border-slate-700/60 hover:bg-[#030712]/70"
                  }`}
                >
                  <div className="flex justify-between items-start gap-2 mb-1.5">
                    <span className="font-bold text-xs text-slate-100 hover:text-sky-400 transition-colors duration-150">
                      {n.name}
                    </span>
                    <Badge variant="outline" className={`font-mono text-[9px] px-1.5 py-0 ${statusBadgeColor}`}>
                      {n.status}
                    </Badge>
                  </div>

                  <p className="text-[10px] text-slate-400 leading-normal line-clamp-2 mb-2 font-mono">
                    {n.description || "Synthesizing supporting media vectors. Active narrative matches public profile targets."}
                  </p>

                  <div className="grid grid-cols-4 gap-2 pt-2 border-t border-[#1F2937]/30 text-[9px] font-mono text-slate-500">
                    <div>
                      <span className="block text-[8px] text-slate-600 uppercase">RISK INDEX</span>
                      <span className={`font-bold ${riskColor}`}>{n.risk} pts</span>
                    </div>
                    <div>
                      <span className="block text-[8px] text-slate-600 uppercase">VELOCITY</span>
                      <span className={`font-bold ${n.trend >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {trendSign}{n.trend?.toFixed(1)}%
                      </span>
                    </div>
                    <div>
                      <span className="block text-[8px] text-slate-600 uppercase">VOLUME</span>
                      <span className="font-bold text-slate-300">{n.mentions} mentions</span>
                    </div>
                    <div className="text-right">
                      <span className="block text-[8px] text-slate-600 uppercase">CONFIDENCE</span>
                      <span className="font-bold text-[#D4AF37]">{n.confidence !== null ? `${n.confidence}%` : "Not Available"}</span>
                    </div>
                  </div>

                  {n.affectedExecs.length > 0 && (
                    <div className="mt-2 pt-1.5 border-t border-dashed border-[#1F2937]/20 flex items-center gap-1.5 text-[8.5px] font-mono text-slate-400">
                      <Users className="h-3 w-3 text-sky-500" />
                      <span className="text-slate-600 font-bold uppercase">TARGETS:</span>
                      <span className="truncate max-w-[220px]">{n.affectedExecs.join(", ")}</span>
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-slate-500 font-mono text-xs py-10">
              No matching narrative vectors found.
            </div>
          )}
        </CardContent>
      </Card>

      {/* CENTER: AI Analysis Details (35% space) */}
      <Card className="col-span-12 lg:col-span-4 bg-[#050B18]/85 border-[#1F2937]/75 shadow-2xl backdrop-blur-md rounded-xl overflow-hidden flex flex-col h-[750px] relative border-l-2 border-l-[#D4AF37]/40">
        <CardHeader className="pb-3 border-b border-[#1F2937]/40 bg-[#030712]/50 p-4">
          <div className="flex justify-between items-center">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-[#D4AF37] flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-[#D4AF37]" /> AI Analysis details
            </CardTitle>
            {activeNarrative && (
              <Badge className="bg-purple-950/30 text-purple-400 border border-purple-800/40 font-mono text-[9px]">
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
                <h3 className="text-sm font-bold text-slate-100 uppercase tracking-tight">{activeNarrative.name}</h3>
                <span className="text-[9px] text-slate-500 block mt-1">LAST AUDITED: {activeNarrative.lastDetected || "TODAY"}</span>
              </div>

              {/* AI generated Narrative Executive Summary */}
              <div className="space-y-1.5">
                <span className="text-[9.5px] text-[#D4AF37] font-bold uppercase tracking-wider block border-b border-[#1F2937]/30 pb-1">AI Executive Summary</span>
                {activeNarrative.summary_text ? (
                  <p className="text-[10px] text-slate-350 leading-relaxed font-mono">
                    {activeNarrative.summary_text}
                  </p>
                ) : (
                  <>
                    <p className="text-[10px] text-slate-350 leading-relaxed font-mono">
                      This reputation coordinate outlines media anomalies targeting public profiles connected to {clientName}. Public traction focuses on {activeNarrative.name.toLowerCase()} with an index intensity rating of {activeNarrative.risk} pts.
                    </p>
                    <p className="text-[10px] text-slate-400 leading-relaxed font-mono mt-1 border-t border-dashed border-[#1F2937]/20 pt-1.5">
                      {activeNarrative.description || "Initial media collection traces narrative volume across digital profiles, indicating low structural risk but high volatile trend vectors in forum discussion boards."}
                    </p>
                  </>
                )}
              </div>

              {/* Metrics Breakdown Grid */}
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div className="bg-[#030712]/40 border border-[#1F2937]/45 rounded p-2 text-center">
                  <span className="text-[8px] text-slate-600 block uppercase font-bold">Risk Index</span>
                  <span className={`text-sm font-bold block mt-0.5 ${activeNarrative.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-400" : activeNarrative.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-amber-400" : "text-sky-400"}`}>{activeNarrative.risk} pts</span>
                  <span className="text-[8px] text-slate-500 block mt-0.5">{activeNarrative.risk >= 60 ? "HIGH PROFILE" : "MONITORED"}</span>
                </div>
                <div className="bg-[#030712]/40 border border-[#1F2937]/45 rounded p-2 text-center">
                  <span className="text-[8px] text-slate-600 block uppercase font-bold">Velocity Index</span>
                  <span className={`text-sm font-bold block mt-0.5 ${activeNarrative.trend >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {activeNarrative.trend >= 0 ? "+" : ""}{activeNarrative.trend?.toFixed(1)}%
                  </span>
                  <span className="text-[8px] text-slate-500 block mt-0.5">{activeNarrative.trend >= 15 ? "EXPANDING" : "STABLE"}</span>
                </div>
              </div>

              {/* Entity relationships */}
              <div className="space-y-2">
                <span className="text-[9.5px] text-[#D4AF37] font-bold uppercase tracking-wider block border-b border-[#1F2937]/30 pb-1">Entity Map</span>
                <div className="space-y-1.5 text-[9.5px]">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Primary Targets:</span>
                    <span className="text-slate-300 font-bold">{activeNarrative.affectedExecs?.join(", ") || "Corporate Management"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Connected Sources:</span>
                    <span className="text-slate-350">{activeNarrative.docsCount} distinct documents</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Reputation Velocity:</span>
                    <span className={`font-bold ${activeNarrative.sentiment >= 0.2 ? "text-emerald-400" : activeNarrative.sentiment <= -0.2 ? "text-red-400" : "text-amber-400"}`}>
                      {activeNarrative.sentiment !== undefined ? activeNarrative.sentiment.toFixed(2) : "0.00"} sentiment
                    </span>
                  </div>
                </div>
              </div>

              {/* Recommended Response Action Plan */}
              <div className="space-y-2">
                <span className="text-[9.5px] text-[#D4AF37] font-bold uppercase tracking-wider block border-b border-[#1F2937]/30 pb-1">Action Recommendations</span>
                <div className="bg-sky-950/20 border border-sky-900/40 rounded p-2.5 text-slate-300 text-[10px] space-y-1.5">
                  <div className="flex gap-1.5 items-start">
                    <CheckCircle2 className="h-3.5 w-3.5 text-sky-400 mt-0.5 shrink-0" />
                    <span>
                      {activeNarrative.risk >= 70 
                        ? "Execute press counter-communication and alert executive communications team." 
                        : "Monitor timeline activity and set alert pipelines for volume spikes above 15%."}
                    </span>
                  </div>
                  <div className="flex gap-1.5 items-start">
                    <CheckCircle2 className="h-3.5 w-3.5 text-sky-400 mt-0.5 shrink-0" />
                    <span>Audit supporting sources checklist to scan for organized narrative distribution.</span>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-slate-500 font-mono text-xs py-20 text-center">
              <BarChart2 className="h-8 w-8 text-slate-600 mb-2" />
              Select a narrative from the registry to view detailed intelligence analysis.
            </div>
          )}
        </CardContent>
      </Card>

      {/* RIGHT: Evidence & Documents (25% space) */}
      <Card className="col-span-12 lg:col-span-3 bg-[#050B18]/85 border-[#1F2937]/75 shadow-2xl backdrop-blur-md rounded-xl overflow-hidden flex flex-col h-[750px] relative border-l-2 border-l-emerald-500/40">
        <CardHeader className="pb-3 border-b border-[#1F2937]/40 bg-[#030712]/50 p-4">
          <div className="flex justify-between items-center">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-[#D4AF37] flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5" /> Source Evidence
            </CardTitle>
            <Badge className="bg-[#030712] text-emerald-400 border border-[#1F2937] font-mono text-[9px]">
              {activeNarrative ? activeNarrative.docsCount : 0} Sources
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="p-3 overflow-y-auto flex-1 space-y-2 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
          {activeNarrative ? (
            activeNarrative.rawDocs && activeNarrative.rawDocs.length > 0 ? (
              activeNarrative.rawDocs.map((doc: any) => {
                const docRiskColor = doc.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-400 bg-red-950/20" : doc.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-amber-400 bg-amber-950/20" : "text-sky-400 bg-sky-950/20";
                const formattedDate = doc.timestamp 
                  ? new Date(doc.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" })
                  : "Unknown";

                // Infer Source Type from the source name
                let typeLabel = "news";
                if (doc.source) {
                  const s = doc.source.toLowerCase();
                  if (s.includes("reddit")) typeLabel = "reddit";
                  else if (s.includes("youtube")) typeLabel = "youtube";
                  else if (s.includes("blog")) typeLabel = "blog";
                  else if (s.includes("forum")) typeLabel = "forum";
                }
                
                let srcBadgeColor = "bg-slate-900/80 text-slate-350 border-slate-800";
                if (typeLabel === "reddit") srcBadgeColor = "bg-orange-950/30 text-orange-400 border-orange-900/30";
                else if (typeLabel === "youtube") srcBadgeColor = "bg-red-950/30 text-red-400 border-red-950/30";
                else if (typeLabel === "news") srcBadgeColor = "bg-blue-950/30 text-blue-400 border-blue-900/30";
                else if (typeLabel === "blog") srcBadgeColor = "bg-purple-950/30 text-purple-400 border-purple-900/30";
                else if (typeLabel === "forum") srcBadgeColor = "bg-teal-950/30 text-teal-400 border-teal-900/30";

                return (
                  <div
                    key={doc.id}
                    onClick={() => onSelectDocument(doc)}
                    className="bg-[#030712]/40 border border-[#1F2937]/55 hover:border-emerald-500/40 hover:bg-[#030712]/75 rounded p-2.5 transition-all duration-150 cursor-pointer space-y-2 group relative"
                  >
                    <div className="flex justify-between items-start gap-2">
                      <span className="font-bold text-[10px] text-slate-200 group-hover:text-sky-400 transition-colors duration-150 line-clamp-2 leading-tight">
                        {doc.title}
                      </span>
                    </div>

                    {/* Metadata fields requested by user */}
                    <div className="grid grid-cols-2 gap-y-1 text-[8px] font-mono text-slate-500 border-t border-[#1F2937]/20 pt-1.5">
                      <div>
                        <span className="text-slate-600">SOURCE:</span> <span className="text-slate-350">{doc.source || "RSS Feed"}</span>
                      </div>
                      <div>
                        <span className="text-slate-600">TYPE:</span> <span className="text-slate-350 capitalize">{typeLabel}</span>
                      </div>
                      <div>
                        <span className="text-slate-600">DATE:</span> <span className="text-slate-350">{formattedDate}</span>
                      </div>
                      <div>
                        <span className="text-slate-600">SENTIMENT:</span> <span className={`font-bold ${doc.sentiment >= 0.2 ? "text-emerald-400" : doc.sentiment <= -0.2 ? "text-red-400" : "text-amber-400"}`}>{doc.sentiment?.toFixed(2) || "0.00"}</span>
                      </div>
                      <div>
                        <span className="text-slate-600">RISK SCORE:</span> <span className={`font-bold ${docRiskColor}`}>{doc.risk || 0}</span>
                      </div>
                    </div>

                    {/* Document control actions - Single Button Requested */}
                    <div className="flex gap-1.5 pt-1.5 border-t border-dashed border-[#1F2937]/25 w-full">
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
                          className="h-5 px-1.5 text-[8.5px] font-mono bg-[#030712] border border-[#1F2937] hover:bg-slate-900 text-sky-400 hover:text-sky-350 flex items-center gap-1 w-full justify-center"
                        >
                          <ExternalLink className="h-2 w-2" /> Open Original Article
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled
                          className="h-5 px-1.5 text-[8.5px] font-mono bg-[#030712] border border-[#1F2937] text-slate-500 flex items-center gap-1 w-full justify-center cursor-not-allowed opacity-50"
                        >
                          Original article unavailable
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-500 font-mono text-xs py-20 text-center">
                <AlertTriangle className="h-5 w-5 text-slate-600 mb-1" />
                No supporting documents found.
              </div>
            )
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-slate-500 font-mono text-xs py-20 text-center">
              No narrative selected.
            </div>
          )}
        </CardContent>
      </Card>
      
    </div>
  );
}
