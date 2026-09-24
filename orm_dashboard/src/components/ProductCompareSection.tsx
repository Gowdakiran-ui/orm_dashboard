import React, { useState, useEffect, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from "recharts";
import { Package, Search, BarChart3, Newspaper, Info, AlertOctagon, X, ExternalLink } from "lucide-react";
import { searchProduct, fetchProductDocuments, fetchTopicDistribution, fetchDocumentDetails } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassPill, glassPrimaryButton, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { TopicOwnershipDefinition } from "@/lib/metricDefinitions";

const MIN_TOPIC_COMPARISON_COUNT = 5;
const SIGNATURE_STORY_COUNT = 5;
const TOPIC_COLORS = ["#D4AF37", "#38BDF8", "#F97316", "#A78BFA", "#34D399", "#F472B6", "#FBBF24", "#60A5FA", "#EF4444", "#14B8A6", "#8B5CF6", "#EAB308", "#EC4899", "#22D3EE", "#84CC16", "#F87171", "#94A3B8"];

function useEntityDocuments(clientId: string | null | undefined, entityId: string | undefined) {
  const [documents, setDocuments] = useState<any[]>([]);
  useEffect(() => {
    if (!clientId || !entityId) {
      setDocuments([]);
      return;
    }
    let cancelled = false;
    fetchProductDocuments(clientId, entityId)
      .then(data => { if (!cancelled) setDocuments(data?.documents || []); })
      .catch(() => { if (!cancelled) setDocuments([]); });
    return () => { cancelled = true; };
  }, [clientId, entityId]);
  return documents;
}

export interface ProductCompareSectionProps {
  clientId?: string | null;
  activeClientName: string;
  competitorEntityId: string;
  competitorName: string;
}

interface ProductSearchState {
  query: string;
  result: any | null;
  loading: boolean;
  errorMsg: string | null;
}

const MAX_SEARCH_POLLS = 450; // ~45 minutes at 6s intervals, same budget as CompetitorsTab/ExecutivesTab search
const SEARCH_POLL_INTERVAL_MS = 6000;

function useProductSearch(clientId: string | null | undefined, parentEntityId: string | undefined) {
  const [state, setState] = useState<ProductSearchState>({ query: "", result: null, loading: false, errorMsg: null });
  const cancelledRef = React.useRef(false);

  useEffect(() => {
    return () => { cancelledRef.current = true; };
  }, []);

  async function poll(query: string, attempt: number) {
    if (cancelledRef.current || !clientId) return;
    try {
      const result = await searchProduct(clientId, query, parentEntityId);
      if (cancelledRef.current) return;
      setState(s => ({ ...s, result }));
      if (result?.status === "searching") {
        if (attempt >= MAX_SEARCH_POLLS) {
          setState(s => ({ ...s, loading: false, errorMsg: "Search is taking longer than expected — try again in a few minutes." }));
          return;
        }
        setTimeout(() => poll(query, attempt + 1), SEARCH_POLL_INTERVAL_MS);
      } else {
        setState(s => ({ ...s, loading: false }));
      }
    } catch (err: any) {
      if (cancelledRef.current) return;
      setState(s => ({ ...s, loading: false, errorMsg: err?.message || "Search failed", result: null }));
    }
  }

  function setQuery(query: string) {
    setState(s => ({ ...s, query }));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const query = state.query.trim();
    if (!clientId || !query) return;
    cancelledRef.current = false;
    setState(s => ({ ...s, loading: true, errorMsg: null, result: null }));
    poll(query, 1);
  }

  return { state, setQuery, submit };
}

// Product-Level Compare, below the existing Competitor Compare view (TASK
// Part 2). Same search-first flow CompetitorsTab/ExecutivesTab already use:
// a client types their own product name (own = the client's brand entity,
// resolved server-side) and the currently-selected competitor's product
// name, each independently polled through the identical
// tracked/searching/insufficient-evidence states. The comparison only
// renders once both sides have cleared INSUFFICIENT_EVIDENCE -- never a
// fabricated pairing.
export function ProductCompareSection({ clientId, activeClientName, competitorEntityId, competitorName }: ProductCompareSectionProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";

  const own = useProductSearch(clientId, undefined);
  const competitor = useProductSearch(clientId, competitorEntityId);

  const ownProduct = own.state.result?.status === "tracked" ? own.state.result.product : null;
  const competitorProduct = competitor.state.result?.status === "tracked" ? competitor.state.result.product : null;

  const bothHaveEvidence =
    ownProduct && ownProduct.health_status !== "INSUFFICIENT_EVIDENCE" &&
    competitorProduct && competitorProduct.health_status !== "INSUFFICIENT_EVIDENCE";

  // Sentiment trajectory + Signature Stories (Product Compare rework, Parts
  // 2/3): one fetch per product of its full 30-day evidence set, only once
  // that product has cleared the evidence threshold -- same discipline as
  // bothHaveEvidence above, never fetched off a product that isn't real yet.
  const ownDocuments = useEntityDocuments(clientId, ownProduct?.entity_id);
  const competitorDocuments = useEntityDocuments(clientId, competitorProduct?.entity_id);

  // Curated top coverage, ranked by |sentiment| -- the same magnitude
  // signal documents.py already formats and shows per-document as
  // "reputation impact" (sentiment * 10). Not the raw feed (Intelligence
  // Stream already covers that).
  function topSignatureStories(docs: any[]) {
    return [...(docs || [])]
      .sort((a, b) => Math.abs(b?.sentiment ?? 0) - Math.abs(a?.sentiment ?? 0))
      .slice(0, SIGNATURE_STORY_COUNT);
  }
  const ownSignatureStories = useMemo(() => topSignatureStories(ownDocuments), [ownDocuments]);
  const competitorSignatureStories = useMemo(() => topSignatureStories(competitorDocuments), [competitorDocuments]);

  // Topic breakdown (Product Compare rework, Part 4): reuses Competitor
  // Compare's Topic Ownership aggregation/endpoint verbatim, scoped to
  // exactly this product pair via entity_ids instead of the default
  // brand-vs-tracked-competitors roster.
  const [topicDistribution, setTopicDistribution] = useState<any[]>([]);
  useEffect(() => {
    if (!clientId || !bothHaveEvidence || !ownProduct?.entity_id || !competitorProduct?.entity_id) {
      setTopicDistribution([]);
      return;
    }
    let cancelled = false;
    fetchTopicDistribution(clientId, [ownProduct.entity_id, competitorProduct.entity_id])
      .then(data => { if (!cancelled) setTopicDistribution(data?.entities || []); })
      .catch(() => { if (!cancelled) setTopicDistribution([]); });
    return () => { cancelled = true; };
  }, [clientId, bothHaveEvidence, ownProduct?.entity_id, competitorProduct?.entity_id]);

  const topicOwnershipData = useMemo(() => {
    const withEvidence = (topicDistribution || []).filter(e => e && e.total_documents > 0);
    if (withEvidence.length === 0) return { chartData: [], topicKeys: [] };
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
      const row: any = { name: e.name };
      topicKeys.forEach(topic => {
        const count = (e.topic_counts || {})[topic] || 0;
        row[topic] = e.total_documents > 0 ? (count / e.total_documents) * 100 : 0;
      });
      return row;
    });
    return { chartData, topicKeys };
  }, [topicDistribution]);

  // Details drawer -- same component/pattern as CompetitorsTab's (title,
  // source, topic chips, original-article snippet, view-source link), kept
  // local to this section since it's the only consumer of ownDocuments/
  // competitorDocuments and CompetitorsTab's own drawer is scoped to
  // competitorEvents, not product coverage.
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedDocUrl, setSelectedDocUrl] = useState<string | null>(null);
  const selectedDoc = useMemo(() => {
    if (!selectedDocId) return null;
    return [...ownDocuments, ...competitorDocuments].find(d => d.id === selectedDocId) || null;
  }, [selectedDocId, ownDocuments, competitorDocuments]);

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

  const cardBorder = isDark ? "border-white/[0.12]" : "border-black/[0.06]";
  const surfaceBg = isDark ? "bg-black/30" : "bg-black/[0.03]";
  const surfaceBorder = isDark ? "border-white/[0.08]" : "border-black/[0.06]";
  const drawerSurface = isDark ? "bg-zinc-950/95 border-white/[0.12]" : "bg-white/95 border-black/[0.06]";
  const chipClass = isDark ? "bg-[#030712] border border-white/[0.10] text-zinc-400" : "bg-black/[0.03] border border-black/[0.08] text-zinc-500";
  const touchTarget = "min-h-[44px] inline-flex items-center justify-center";

  function renderSignatureStories(label: string, docs: any[]) {
    return (
      <div className="space-y-2">
        <span className={`block text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>{label}</span>
        {docs.length === 0 ? (
          <p className={`text-xs font-mono ${mutedText(theme)}`}>No qualifying coverage in the last 30 days yet.</p>
        ) : (
          <div className="space-y-2">
            {docs.map(doc => (
              <button
                key={doc.id}
                onClick={() => setSelectedDocId(doc.id)}
                className={`w-full text-left rounded p-3 border transition-colors ${isDark ? "border-white/[0.08] bg-black/20 hover:border-white/[0.2]" : "border-black/[0.06] bg-black/[0.02] hover:border-black/[0.15]"}`}
              >
                <p className={`text-xs font-mono truncate ${bodyText(theme)}`}>{doc.title}</p>
                <div className="flex items-center gap-2 mt-1 text-[11px] font-mono">
                  <span className={mutedText(theme)}>{doc.source}</span>
                  <span className={mutedText(theme)}>•</span>
                  <span className={(doc.sentiment ?? 0) >= 0 ? "text-emerald-500" : "text-red-500"}>
                    {doc.reputation_impact}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  function renderSearchBox(label: string, hook: ReturnType<typeof useProductSearch>, placeholder: string) {
    const { state, setQuery, submit } = hook;
    return (
      <div className="space-y-3">
        <span className={`block text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>{label}</span>
        <form onSubmit={submit} className="flex gap-2">
          <input
            type="text"
            value={state.query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={placeholder}
            className={`flex-1 rounded px-3 py-2 text-xs font-mono focus:outline-none ${bodyText(theme)} ${isDark ? "bg-zinc-950/60 border border-white/[0.12] placeholder:text-zinc-600 focus:border-[#00F5D4]/50" : "bg-white/60 border border-black/[0.08] placeholder:text-zinc-400 focus:border-[#3B82F6]/50"}`}
          />
          <button
            type="submit"
            disabled={state.loading || !state.query.trim()}
            className={`disabled:opacity-50 disabled:cursor-not-allowed font-mono text-xs px-4 py-2 whitespace-nowrap ${glassPrimaryButton(theme)}`}
          >
            {state.loading ? "Searching..." : "Search"}
          </button>
        </form>

        {state.errorMsg && <p className="text-red-500 font-mono text-xs">{state.errorMsg}</p>}

        {state.result?.status === "searching" && (
          <div className={`rounded-2xl p-4 flex items-center space-x-3 border ${isDark ? "border-[#00F5D4]/30 bg-black/30" : "border-[#3B82F6]/30 bg-black/[0.03]"}`}>
            <div className="h-3 w-3 rounded-full animate-pulse" style={{ backgroundColor: accent }} />
            <p className={`text-xs font-mono ${mutedText(theme)}`}>
              Running a fresh scoped search — collecting and scoring coverage for this product. This can take a moment.
            </p>
          </div>
        )}

        {state.result?.status === "tracked" && (
          <div className={`rounded-2xl p-4 space-y-2 border ${isDark ? "border-[#00F5D4]/30 bg-black/30" : "border-[#3B82F6]/30 bg-black/[0.03]"}`}>
            <div className="flex items-center justify-between">
              <span className={`font-mono text-sm font-bold ${bodyText(theme)}`}>{state.result.product.name}</span>
              <Badge className={glassPill(theme)} style={{ color: accent }}>TRACKED</Badge>
            </div>
            {state.result.product.health_status === "INSUFFICIENT_EVIDENCE" ? (
              <p className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>
                No qualifying coverage found yet — tracked, but not enough evidence to score
              </p>
            ) : (
              <div className="grid grid-cols-4 gap-3 text-xs font-mono">
                <div>
                  <span className={`block ${mutedText(theme)}`}>Reputation</span>
                  <span className="font-bold text-sm" style={{ color: accent }}>
                    {state.result.product.reputation_score !== null ? state.result.product.reputation_score.toFixed(2) : "N/A"}
                  </span>
                </div>
                <div>
                  <span className={`block ${mutedText(theme)}`}>Rank</span>
                  <span className={bodyText(theme)}>{state.result.product.rank ? `#${state.result.product.rank}` : "Unranked"}</span>
                </div>
                <div>
                  <span className={`block ${mutedText(theme)}`}>Risk</span>
                  <span className={bodyText(theme)}>{state.result.product.risk_score !== null ? state.result.product.risk_score.toFixed(1) : "N/A"}</span>
                </div>
                <div>
                  <span className={`block ${mutedText(theme)}`}>Share of Voice</span>
                  <span className={bodyText(theme)}>{state.result.product.share_of_voice !== null ? `${state.result.product.share_of_voice.toFixed(1)}%` : "N/A"}</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <Card className={glassCard(theme)}>
      <div className={SPECULAR_LINE} />
      <CardHeader className={`pb-3 border-b ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
        <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
          <Package className="h-4 w-4 mr-2" style={{ color: accent }} />
          Product Compare
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {renderSearchBox(`${activeClientName}'s Product`, own, "Search your product name...")}
          {renderSearchBox(`${competitorName}'s Product`, competitor, "Search their product name...")}
        </div>

        {!bothHaveEvidence && (ownProduct || competitorProduct) && (
          <p className={`text-xs font-mono uppercase tracking-wider text-center ${mutedText(theme)}`}>
            <Search className="h-3 w-3 inline mr-1" />
            Waiting for both products to clear evidence threshold before rendering comparison.
          </p>
        )}

        {bothHaveEvidence && (
          <>
            {/* Signature Stories -- curated top coverage, not the raw feed. */}
            <div className="space-y-3 pt-2">
              <span className={`flex items-center text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>
                <Newspaper className="h-4 w-4 mr-2" style={{ color: accent }} />
                Signature Stories
              </span>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {renderSignatureStories(ownProduct.name, ownSignatureStories)}
                {renderSignatureStories(competitorProduct.name, competitorSignatureStories)}
              </div>
            </div>

            {/* Topic breakdown -- reuses Competitor Compare's Topic Ownership
                aggregation/chart, scoped to this product pair. */}
            <div className="space-y-3 pt-2">
              <span className={`flex items-center text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>
                <BarChart3 className="h-4 w-4 mr-2" style={{ color: accent }} />
                Topic Breakdown
                <InfoTooltip label="About Topic Ownership"><TopicOwnershipDefinition /></InfoTooltip>
              </span>
              <p className={`text-[11px] font-mono leading-relaxed ${mutedText(theme)}`}>
                Uses a shared 17-topic taxonomy applied identically across every client — a category can read as
                structurally irrelevant for this client&apos;s industry. Treat this chart as directional, not precise.
              </p>
              {topicOwnershipData.chartData.length > 0 ? (
                <div className="h-[300px]">
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
                <p className={`text-xs font-mono text-center py-8 ${mutedText(theme)}`}>
                  Not enough qualifying coverage in the last 30 days to compare topics for this pair yet.
                </p>
              )}
            </div>
          </>
        )}
      </CardContent>

      {/* Details Drawer -- same pattern as CompetitorsTab's (title, source,
          topic chip, original-article snippet, view-source link). */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 overflow-hidden font-mono">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setSelectedDocId(null)} />
          <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
            <div className={`w-[600px] backdrop-blur-2xl border-l flex flex-col justify-between shadow-2xl animate-in slide-in-from-right duration-300 ${bodyText(theme)} ${drawerSurface}`}>
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

              <div className="flex-1 overflow-y-auto overflow-x-hidden p-6 space-y-6">
                <div className="space-y-2">
                  <h3 className={`text-sm font-bold leading-snug ${bodyText(theme)}`}>{selectedDoc.title}</h3>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Source: {selectedDoc.source}</span>
                    <span className={`px-2 py-0.5 rounded ${chipClass}`}>Topic: {selectedDoc.topic}</span>
                  </div>
                </div>

                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold flex items-center ${mutedText(theme)}`}>
                    <Info className="h-3.5 w-3.5 mr-1 text-[#D4AF37]" /> Original Article Snippet
                  </span>
                  <div className={`border p-4 rounded text-xs leading-relaxed max-h-48 overflow-y-auto overflow-x-hidden whitespace-pre-wrap ${mutedText(theme)} ${surfaceBorder} ${surfaceBg}`}>
                    {selectedDoc.original_content || "No original content available."}
                  </div>
                </div>
              </div>

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
    </Card>
  );
}
