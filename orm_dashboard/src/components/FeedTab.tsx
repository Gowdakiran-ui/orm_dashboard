import { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from 'next/link';
import {
  Activity,
  ExternalLink, Cpu, TrendingUp, CheckCircle2,
  AlertTriangle, Info, Sparkles, Clock, X
} from "lucide-react";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";
import { isValidOriginalArticleUrl } from "@/utils/urlValidation";
import { fetchDocumentDetails } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { isPlaceholderTitle, PreviewUnavailableLabel, PLACEHOLDER_ROW_CLASS } from "@/components/ui/PreviewUnavailable";


// Real ingest-time source categories (Document.document_type, exposed by
// _build_document_responses in orm_collection/app/api/endpoints/documents.py)
// -- confirmed live distribution: rss, youtube, gdelt, hn_algolia, instagram,
// reddit, zero nulls. `gdelt` and `hn_algolia` are grouped into "RSS Feeds"
// rather than given their own pills: both are link/no-full-text aggregator
// sources (hn_algolia.py's own docstring: "same 'no full text available'
// pattern as the RSS/GDELT adapters"), so to a non-technical user they read
// as the same kind of thing RSS is, unlike Reddit's genuine forum content.
const SOURCE_TYPE_GROUPS: { key: string; label: string; types: string[] }[] = [
  { key: "rss", label: "RSS Feeds", types: ["rss", "gdelt", "hn_algolia"] },
  { key: "youtube", label: "YouTube", types: ["youtube"] },
  { key: "instagram", label: "Instagram", types: ["instagram"] },
  { key: "reddit", label: "Reddit", types: ["reddit"] },
];

export interface FeedTabProps {
  documentsLoading: boolean;
  documentsError: string | null;
  documents: any[];
  executives?: any[];
  systemStatus?: any;
  clientId?: string | null;
}

export function FeedTab({
  documentsLoading,
  documentsError,
  documents = [],
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
  // xoop_ui_clarity_review.md: mounting all ~500 documents' worth of feed
  // cards at once (no windowing) caused blank scroll regions and a
  // screenshot timeout during normal scrolling. Rendering only a bounded
  // window at a time (already-recency-sorted by the backend, see
  // documents.py order_by) fixes the DOM-node count without adding a
  // virtualization dependency.
  const FEED_PAGE_SIZE = 50;
  const [feedRenderCount, setFeedRenderCount] = useState(FEED_PAGE_SIZE);

  // Source-type filter pills above the ingest stream -- display-layer filter
  // over the already-fetched `documents` array, no extra fetch per source.
  const [selectedSourceGroup, setSelectedSourceGroup] = useState<string>("all");

  const filteredDocuments = useMemo(() => {
    if (selectedSourceGroup === "all") return documents;
    const group = SOURCE_TYPE_GROUPS.find(g => g.key === selectedSourceGroup);
    if (!group) return documents;
    return documents.filter(d => d && group.types.includes(d.document_type));
  }, [documents, selectedSourceGroup]);

  // Reset paging when the source filter changes so "Load more" starts from
  // the top of the newly-filtered list instead of an index sized for the
  // previous (likely larger) unfiltered/differently-filtered list.
  useEffect(() => {
    setFeedRenderCount(FEED_PAGE_SIZE);
  }, [selectedSourceGroup]);

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

  return (
    <ErrorBoundary fallback={<TelemetryErrorWidget title="Intelligence Stream Panel Error" />}>
      {documentsLoading ? (
        <div className="space-y-6">
          {/* Skeleton for the Real-Time Brand Ingest Stream -- the only
              section this page shows now (client-facing: showing full
              collection mechanics undercuts the ORM service, so metrics/
              timeline/source/risk-distribution telemetry was removed). */}
          <Card className={`${glassTokens[theme].card} rounded-3xl h-[780px] animate-pulse`}>
            <CardHeader className="space-y-2">
              <div className={`h-4 rounded w-1/3 ${isDark ? "bg-white/[0.08]" : "bg-black/[0.06]"}`} />
            </CardHeader>
            <CardContent className="space-y-4">
              {[1, 2, 3, 4, 5, 6].map(x => (
                <div key={x} className={`h-16 rounded ${isDark ? "bg-white/[0.04]" : "bg-black/[0.03]"}`} />
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

          {/* Real-Time Ingested Feed List. Document Intelligence Details used
              to be a separate tab; it's now a per-row Details button that
              opens a slide-over drawer for that row's document, same
              pattern as ExecutivesTab.tsx's per-row Details drawer. */}
          <Card className={`${glassCard(theme)} overflow-hidden flex flex-col h-[780px]`}>
            <div className={SPECULAR_LINE} />
            <CardHeader className={`pb-3 border-b p-4 ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
              <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 ${mutedText(theme)}`}>
                <Activity className="h-3.5 w-3.5 text-emerald-400" /> Real-time Brand Ingest Stream
              </CardTitle>
              <CardDescription className={`text-[9px] font-mono ${mutedText(theme)}`}>Real-time matching documents</CardDescription>
              {/* Source-type filter pills -- filters the already-fetched
                  `documents` array client-side, no per-source fetch. */}
              <div className="flex flex-wrap gap-1.5 pt-3">
                {[{ key: "all", label: "All" }, ...SOURCE_TYPE_GROUPS].map(group => {
                  const isActive = selectedSourceGroup === group.key;
                  return (
                    <button
                      key={group.key}
                      type="button"
                      onClick={() => setSelectedSourceGroup(group.key)}
                      className={`min-h-[44px] inline-flex items-center justify-center px-3 rounded-full border text-[10px] font-mono font-bold uppercase tracking-wider transition-colors ${
                        isActive
                          ? "text-black"
                          : isDark ? "border-white/[0.12] text-zinc-400 hover:text-zinc-200 hover:border-white/[0.2]" : "border-black/[0.08] text-zinc-500 hover:text-zinc-800 hover:border-black/[0.15]"
                      }`}
                      style={isActive ? { backgroundColor: accent, borderColor: accent } : undefined}
                    >
                      {group.label}
                    </button>
                  );
                })}
              </div>
            </CardHeader>
            <CardContent key={selectedSourceGroup} className="p-3 overflow-y-auto flex-1 space-y-2.5 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent animate-in fade-in slide-in-from-right-4 duration-300">
              {filteredDocuments.slice(0, feedRenderCount).map((d, i) => {
                const docRiskColor = d.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-400 border-red-950/40 bg-red-950/20" : d.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-amber-400 border-amber-950/40 bg-amber-950/20" : "text-sky-400 border-sky-950/40 bg-sky-950/20";

                // Timestamp formatter
                const formattedTime = d.timestamp
                  ? new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                  : "Recent";
                const isPlaceholder = isPlaceholderTitle(d.title, d.source);

                return (
                  <div
                    key={d.id ?? i}
                    className={`border rounded-lg p-3 transition-all duration-200 font-mono text-[10px] space-y-2 ${
                      isDark ? "bg-black/20 border-white/[0.08] hover:border-white/[0.2] hover:bg-black/30" : "bg-black/[0.02] border-black/[0.06] hover:border-black/[0.15] hover:bg-black/[0.04]"
                    } ${isPlaceholder ? PLACEHOLDER_ROW_CLASS : ""}`}
                  >
                    <div className="flex justify-between items-start gap-2">
                      <span className={`font-bold text-xs line-clamp-2 leading-tight transition-colors duration-150 ${bodyText(theme)}`}>
                        {isPlaceholder ? <PreviewUnavailableLabel /> : d.title}
                      </span>
                      <span className={`text-[9px] shrink-0 flex items-center gap-1 font-bold ${mutedText(theme)}`}>
                        <Clock className="h-3 w-3" /> {formattedTime}
                      </span>
                    </div>

                    <div className={`flex flex-wrap items-center gap-1.5 pt-1.5 border-t ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
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
                      <button
                        type="button"
                        onClick={() => setSelectedDocId(d.id)}
                        className="ml-auto bg-blue-600 hover:bg-blue-700 cursor-pointer text-white font-mono text-xs font-bold rounded px-3 min-h-[44px] inline-flex items-center justify-center"
                      >
                        Details
                      </button>
                    </div>
                  </div>
                );
              })}
              {filteredDocuments.length === 0 && (
                <div className={`flex flex-col items-center justify-center h-full font-mono text-xs py-20 text-center ${mutedText(theme)}`}>
                  <AlertTriangle className={`h-8 w-8 mb-2 ${mutedText(theme)}`} />
                  {selectedSourceGroup === "all"
                    ? "No intelligence documents matches in database."
                    : `No ${SOURCE_TYPE_GROUPS.find(g => g.key === selectedSourceGroup)?.label || "matching"} documents for this client.`}
                </div>
              )}
              {filteredDocuments.length > feedRenderCount && (
                <button
                  type="button"
                  onClick={() => setFeedRenderCount((c) => c + FEED_PAGE_SIZE)}
                  className={`w-full text-center text-[10px] font-mono uppercase tracking-wider py-2.5 rounded-lg border ${isDark ? "border-white/[0.08] text-zinc-400 hover:bg-white/[0.03]" : "border-black/[0.06] text-zinc-600 hover:bg-black/[0.02]"}`}
                >
                  Load {Math.min(FEED_PAGE_SIZE, filteredDocuments.length - feedRenderCount)} more ({feedRenderCount} of {filteredDocuments.length})
                </button>
              )}
            </CardContent>
          </Card>

          {/* Document Intelligence Details -- slide-over drawer for the
              document whose row's Details button was clicked. */}
          {selectedDocId && (
            <div className="fixed inset-0 z-50 overflow-hidden font-mono">
              <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setSelectedDocId(null)} />
              <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
                <div className={`w-[600px] backdrop-blur-2xl border-l flex flex-col shadow-2xl animate-in slide-in-from-right duration-300 ${bodyText(theme)} ${isDark ? "bg-zinc-950/95 border-white/[0.12]" : "bg-white/95 border-black/[0.06]"}`}>

                  {/* Header */}
                  <div className={`p-6 border-b flex items-center justify-between ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
                    <div className="flex items-center space-x-3">
                      <Sparkles className="h-5 w-5" style={{ color: accent }} />
                      <span className="text-sm font-bold uppercase">Document Intelligence Details</span>
                    </div>
                    <button
                      onClick={() => setSelectedDocId(null)}
                      className={`flex items-center gap-1.5 text-xs transition-colors ${mutedText(theme)} ${isDark ? "hover:text-zinc-100" : "hover:text-zinc-900"}`}
                    >
                      <X className="h-5 w-5" />
                      <span>Close</span>
                    </button>
                  </div>

                  {/* Content Panel */}
                  <div className={`flex-1 overflow-y-auto p-6 space-y-4 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent font-mono text-xs ${bodyText(theme)}`}>
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
                          {selectedDocDetails.narrative?.name && (
                            <div>
                              <span className="text-[8px] dash-muted uppercase block font-bold">Associated Narrative</span>
                              <span className="dash-strong truncate block max-w-[150px]">{selectedDocDetails.narrative.name}</span>
                            </div>
                          )}
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
                        Failed to load document details.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

        </div>
      )}
    </ErrorBoundary>
  );
}
