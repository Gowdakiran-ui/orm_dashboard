import React, { useCallback, useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassPill, glassPrimaryButton, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { fetchAiCheck, runAiCheck } from "@/lib/api";
import {
  parseAiCheck, estimateSentence, runLine, stabilityTone, REMOVAL_LIST_TITLE, REMOVAL_LIST_NOTICE, CARD_NOTICE, groupRemovalCandidates,
  type AiCheckView, type AiEstimate, type AiPage, type AiPrompt, type AiSource,
} from "@/utils/aiCheck";

// "What AI says about you" (Brand Equity). Self-fetching: it shows nothing at all while the feature is switched off on the
// server (AI_CHECK_ENABLED) or the request fails. It changes no score. Starting a run is a super-admin action, confirmed
// against a printed cost estimate; the internal removal-candidates list is only ever sent to super admins.

const POLL_MS = 10000;
const POLL_MAX_MS = 25 * 60 * 1000;

const TIER_CHIP: Record<string, string> = {
  high: "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20",
  medium: "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20",
  official: "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20",
  own: "bg-zinc-500/10 text-zinc-500 border border-zinc-500/20",
  low: "bg-orange-500/10 text-orange-500 border border-orange-500/20",
  user_generated: "bg-orange-500/10 text-orange-500 border border-orange-500/20",
  unrated: "bg-yellow-500/10 text-yellow-600 border border-yellow-500/20",
};

function ReliabilityChip({ tier, label }: { tier: string; label: string }) {
  return (
    <span data-testid="reliability-chip" className={`inline-block rounded px-1.5 py-0.5 font-mono text-[11px] font-bold leading-none ${TIER_CHIP[tier] ?? TIER_CHIP.unrated}`}>
      {label}
    </span>
  );
}

function isHttp(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

function PageList({ pages, muted }: { pages: AiPage[]; muted: string }) {
  return (
    <ul className="space-y-2 text-xs">
      {pages.map(p => (
        <li key={p.url} className="flex flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2">
            {isHttp(p.url) ? (
              <a href={p.url} target="_blank" rel="noopener noreferrer" className="font-bold hover:underline break-all">{p.title || p.url}</a>
            ) : (
              <span className="font-bold break-all">{p.title || p.url}</span>
            )}
            <ReliabilityChip tier={p.tier} label={p.reliability} />
          </span>
          <span className={muted}>
            {p.domain} · cited in {p.citedInAnswers} {p.citedInAnswers === 1 ? "answer" : "answers"} · {p.questions.join(", ")}
          </span>
        </li>
      ))}
    </ul>
  );
}

function SourceChips({ sources }: { sources: AiSource[] }) {
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      {sources.map(s => (
        <span key={s.domain} className="inline-flex items-center gap-1.5 text-xs">
          <span className="font-mono">{s.domain}</span>
          <ReliabilityChip tier={s.tier} label={s.reliability} />
        </span>
      ))}
    </span>
  );
}

function StabilityMarker({ p }: { p: AiPrompt }) {
  const tone = stabilityTone(p);
  const cls = tone === "same" ? "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20"
    : tone === "varies" ? "bg-yellow-500/10 text-yellow-600 border border-yellow-500/20"
    : "bg-zinc-500/10 text-zinc-500 border border-zinc-500/20";
  const word = tone === "same" ? "Same sources" : tone === "varies" ? "Sources vary" : "One run";
  return (
    <span title={p.stability} data-testid="stability-marker" data-tone={tone} className={`inline-block rounded px-1.5 py-0.5 font-mono text-[11px] font-bold leading-none ${cls}`}>
      {word}
    </span>
  );
}

export interface AiCheckCardProps {
  clientId: string | null;
}

export function AiCheckCard({ clientId }: AiCheckCardProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [view, setView] = useState<AiCheckView | null>(null);
  const [confirm, setConfirm] = useState<AiEstimate | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const startedPolling = useRef<number | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!clientId) return;
    try {
      setView(parseAiCheck(await fetchAiCheck(clientId, signal)));
    } catch {
      if (!signal?.aborted) setView(null);
    }
  }, [clientId]);

  useEffect(() => {
    setView(null);
    setConfirm(null);
    setActionError(null);
    const ctl = new AbortController();
    load(ctl.signal);
    return () => ctl.abort();
  }, [clientId, load]);

  // While a run is going, look again every 10 s (for at most 25 minutes).
  const running = view?.run?.status === "running";
  useEffect(() => {
    if (!running) { startedPolling.current = null; return; }
    if (startedPolling.current === null) startedPolling.current = Date.now();
    const t = setInterval(() => {
      if (Date.now() - (startedPolling.current ?? Date.now()) > POLL_MAX_MS) { clearInterval(t); return; }
      load();
    }, POLL_MS);
    return () => clearInterval(t);
  }, [running, load]);

  const beginRun = async () => {
    if (!clientId) return;
    setBusy(true); setActionError(null);
    try {
      const r = await runAiCheck(clientId, true);
      const e = r?.estimate;
      if (!e || typeof e.calls !== "number" || typeof e.estimated_cost_usd !== "number") throw new Error("The cost estimate is unavailable.");
      setConfirm({ calls: e.calls, prompts: e.prompts ?? 0, repeats: e.repeats ?? 0, estimatedCostUsd: e.estimated_cost_usd, capUsd: e.cap_usd ?? 0 });
    } catch (err: any) {
      setActionError(err?.message || "Could not prepare the AI check.");
    } finally { setBusy(false); }
  };

  const confirmRun = async () => {
    if (!clientId) return;
    setBusy(true); setActionError(null);
    try {
      await runAiCheck(clientId, false);
      setConfirm(null);
      await load();
    } catch (err: any) {
      setActionError(err?.message || "Could not start the AI check.");
    } finally { setBusy(false); }
  };

  if (!clientId || !view || !view.enabled) return null;

  const muted = mutedText(theme);
  const body = bodyText(theme);
  const divider = isDark ? "border-white/[0.08]" : "border-black/[0.06]";

  return (
    <Card className={glassCard(theme)} data-testid="ai-check-card">
      <div className={SPECULAR_LINE} />
      <CardContent className="p-5 space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1 max-w-3xl">
            <h3 className={`text-sm font-bold uppercase tracking-wider ${body}`}>What AI says about you</h3>
            <p className={`text-xs ${muted}`}>{CARD_NOTICE}</p>
            <p className={`text-xs font-mono ${muted}`} data-testid="ai-check-run-line">{runLine(view.run)}</p>
          </div>
          {view.canRun && !confirm && (
            <button
              type="button" onClick={beginRun} disabled={busy || running}
              className={`px-4 py-2 text-xs uppercase tracking-wider min-h-[44px] disabled:opacity-50 ${glassPrimaryButton(theme)}`}
            >
              {running ? "Running…" : "Run AI check"}
            </button>
          )}
        </div>

        {confirm && (
          <div className={`rounded-2xl border p-4 space-y-3 ${divider}`} data-testid="ai-check-confirm">
            <p className={`text-xs ${body}`}>{estimateSentence(confirm)} This is paid. Continue?</p>
            <div className="flex gap-3">
              <button type="button" onClick={confirmRun} disabled={busy} className={`px-4 py-2 text-xs min-h-[44px] disabled:opacity-50 ${glassPrimaryButton(theme)}`}>
                {busy ? "Starting…" : "Yes, run it"}
              </button>
              <button type="button" onClick={() => setConfirm(null)} disabled={busy} className={`px-4 py-2 text-xs min-h-[44px] ${muted} hover:underline`}>Cancel</button>
            </div>
          </div>
        )}
        {actionError && <p className="text-xs text-red-500" role="alert">{actionError}</p>}

        {view.prompts.length > 0 && (
          <div className="space-y-4">
            {view.prompts.map(p => (
              <div key={p.key} className={`border-t pt-4 space-y-2 ${divider}`} data-testid="ai-check-prompt">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-xs font-bold ${body}`}>{p.label}</span>
                  <StabilityMarker p={p} />
                </div>
                <p className={`text-xs ${muted}`}>{p.question}</p>
                <p className={`text-sm leading-relaxed ${body}`}>{p.shortAnswer || "No answer text."}</p>
                {p.sources.length > 0 ? <SourceChips sources={p.sources} /> : <span className={`text-xs ${muted}`}>No pages were cited.</span>}
              </div>
            ))}
          </div>
        )}

        {view.run && view.run.status !== "running" && view.prompts.length > 0 && (
          <div className={`border-t pt-4 space-y-2 ${divider}`} data-testid="ai-check-low-pages">
            <span className={`text-xs font-bold uppercase tracking-wider ${body}`}>
              Cited pages from low-reliability outlets ({view.lowReliabilityPages.length})
            </span>
            {view.lowReliabilityPages.length > 0
              ? <PageList pages={view.lowReliabilityPages} muted={muted} />
              : <p className={`text-xs ${muted}`}>None of the cited pages came from a low-reliability outlet.</p>}
          </div>
        )}

        {view.canRun && view.removalCandidates.length > 0 && (
          <div className="rounded-2xl border border-yellow-500/30 p-4 space-y-3" data-testid="removal-candidates">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-xs font-bold uppercase tracking-wider ${body}`}>{REMOVAL_LIST_TITLE}</span>
              <Badge className={`${glassPill(theme)} text-yellow-600 font-mono text-[11px]`}>Internal</Badge>
              <Badge className={`${glassPill(theme)} text-yellow-600 font-mono text-[11px]`}>Needs legal review</Badge>
            </div>
            <p className={`text-xs ${muted}`}>{REMOVAL_LIST_NOTICE}</p>
            {groupRemovalCandidates(view.removalCandidates).map(g => (
              <div key={g.key} className="space-y-2" data-testid={`removal-group-${g.key}`}>
                <span className={`text-xs font-bold ${body}`}>{g.label} ({g.pages.length})</span>
                <PageList pages={g.pages} muted={muted} />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
