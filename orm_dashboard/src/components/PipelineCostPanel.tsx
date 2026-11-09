import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { fetchPipelineCost } from "@/lib/api";
import {
  parsePipelineCost, formatCost, apifyLine, llmLine, searchLine, runLine, PIPELINE_COST_NOTE, type CostBreakdownRow, type PipelineCostState,
} from "@/utils/pipelineCost";

// Last Run Pipeline cost for the active company. Super admins only: it is mounted inside the Admin tab, which only they can open, and
// the endpoint itself refuses everyone else. It reads a table nothing else reads and changes no score.

function Rows({ rows, muted }: { rows: CostBreakdownRow[]; muted: string }) {
  if (rows.length === 0) return null;
  return (
    <ul className={`mt-1 space-y-0.5 text-xs ${muted}`}>
      {rows.map(r => (
        <li key={r.key} data-testid="cost-row">
          {r.key}: {r.calls} {r.calls === 1 ? "call" : "calls"}, {r.usd === null ? "not costed" : formatCost(r.usd)}{r.note ? ` · ${r.note}` : ""}
        </li>
      ))}
    </ul>
  );
}

export function PipelineCostPanel({ clientId }: { clientId: string | null }) {
  const { theme } = useTheme();
  const [state, setState] = useState<PipelineCostState | "loading">("loading");

  useEffect(() => {
    if (!clientId) { setState({ state: "empty" }); return; }
    setState("loading");
    const ctl = new AbortController();
    fetchPipelineCost(clientId, ctl.signal)
      .then(p => { if (!ctl.signal.aborted) setState(parsePipelineCost(p)); })
      .catch(() => { if (!ctl.signal.aborted) setState({ state: "unavailable" }); });
    return () => ctl.abort();
  }, [clientId]);

  const muted = mutedText(theme);
  const body = bodyText(theme);

  return (
    <Card className={glassCard(theme)} data-testid="pipeline-cost-panel">
      <div className={SPECULAR_LINE} />
      <CardContent className="p-5 space-y-3 font-mono">
        <h3 className={`text-sm font-bold uppercase tracking-wider ${body}`}>Last Run Pipeline cost</h3>
        {state === "loading" && <p className={`text-xs ${muted}`}>Loading…</p>}
        {state !== "loading" && state.state === "unavailable" && <p className={`text-xs ${muted}`}>The cost is unavailable right now.</p>}
        {state !== "loading" && state.state === "empty" && <p className={`text-xs ${muted}`}>No pipeline run has been metered for this company yet.</p>}
        {state !== "loading" && state.state === "ready" && (
          <>
            <p className={`text-xs ${muted}`} data-testid="cost-run-line">{runLine(state.cost)}</p>
            <p className={`text-2xl font-bold ${body}`} data-testid="cost-total">{formatCost(state.cost.totalUsd)}</p>
            <div className="space-y-2 text-xs">
              <div><span className={`font-bold ${body}`}>Apify</span><span className={muted}> · {apifyLine(state.cost)}</span><Rows rows={state.cost.apify.rows} muted={muted} /></div>
              <div><span className={`font-bold ${body}`}>LLM</span><span className={muted}> · {llmLine(state.cost)}</span><Rows rows={state.cost.llm.rows} muted={muted} /></div>
              <div><span className={`font-bold ${body}`}>Search</span><span className={muted}> · {searchLine(state.cost)}</span></div>
            </div>
          </>
        )}
        <p className={`text-xs ${muted}`}>{PIPELINE_COST_NOTE}</p>
      </CardContent>
    </Card>
  );
}
