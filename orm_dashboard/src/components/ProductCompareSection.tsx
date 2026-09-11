import React, { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Package, Search } from "lucide-react";
import { searchProduct } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassPill, glassPrimaryButton, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";

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

        {bothHaveEvidence && (
          <div className="grid grid-cols-4 gap-3 text-xs font-mono pt-2">
            <div />
            <div className={`text-center ${mutedText(theme)}`}>{ownProduct.name}</div>
            <div className={`text-center ${mutedText(theme)}`}>{competitorProduct.name}</div>
            <div />
            {[
              ["Reputation", ownProduct.reputation_score, competitorProduct.reputation_score, (v: number) => v.toFixed(2)],
              ["Risk", ownProduct.risk_score, competitorProduct.risk_score, (v: number) => v.toFixed(1)],
              ["Share of Voice", ownProduct.share_of_voice, competitorProduct.share_of_voice, (v: number) => `${v.toFixed(1)}%`],
            ].map(([label, a, b, fmt]: any) => (
              <React.Fragment key={label}>
                <div className={mutedText(theme)}>{label}</div>
                <div className={`text-center font-bold ${bodyText(theme)}`}>{a !== null ? fmt(a) : "N/A"}</div>
                <div className={`text-center font-bold ${bodyText(theme)}`}>{b !== null ? fmt(b) : "N/A"}</div>
                <div />
              </React.Fragment>
            ))}
          </div>
        )}

        {!bothHaveEvidence && (ownProduct || competitorProduct) && (
          <p className={`text-xs font-mono uppercase tracking-wider text-center ${mutedText(theme)}`}>
            <Search className="h-3 w-3 inline mr-1" />
            Waiting for both products to clear evidence threshold before rendering comparison.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
