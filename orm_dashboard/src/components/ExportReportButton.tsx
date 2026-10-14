"use client";

// Header button that exports the Brand Equity, Risk Center and Executive Analytics pages for the selected client as a PDF.
//
// On click, in this order: (1) take ONE snapshot of everything the report needs (so a 45-second re-poll or a client
// switch mid-export cannot mix data), (2) build the report model from that snapshot only, (3) mount the hidden chart
// stage with the snapshot and capture the charts, (4) load the PDF libraries (dynamic import) and render, (5) download.
import React, { useCallback, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { FileDown, Loader2 } from "lucide-react";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassPrimaryButton } from "@/components/theme/tokens";
import { ExportReportStage } from "@/components/ExportReportStage";
import { buildReportModel, type ChartId, type ReportInput } from "@/utils/reportModel";
import type { ChartImage } from "@/lib/exportReport";
import type { WantedChart } from "@/lib/captureCharts";

export interface ExportReportButtonProps {
  // Called once per click; returns the current dashboard state for the selected client.
  getSnapshot: () => ReportInput;
  disabled: boolean;
  disabledReason?: string;
}

type Phase = "idle" | "preparing";

interface StageRequest { input: ReportInput; wanted: WantedChart[] }

function download(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export function ExportReportButton({ getSnapshot, disabled, disabledReason }: ExportReportButtonProps) {
  const { theme } = useTheme();
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<StageRequest | null>(null);
  const pending = useRef<{ resolve: (c: Partial<Record<ChartId, ChartImage>>) => void; reject: (e: Error) => void } | null>(null);

  const onStageDone = useCallback((c: Partial<Record<ChartId, ChartImage>>) => pending.current?.resolve(c), []);
  const onStageError = useCallback((e: Error) => pending.current?.reject(e), []);

  async function handleClick() {
    if (disabled || phase !== "idle") return;
    setError(null);
    setPhase("preparing");
    try {
      // (1) one snapshot, copied so later state updates cannot change it; (2) the model is built from it right away.
      const input = structuredClone(getSnapshot());
      const model = buildReportModel(input);
      const wanted: WantedChart[] = model.sections
        .flatMap(s => s.blocks)
        .flatMap(b => (b.type === "chart" ? [{ id: b.id, title: b.title }] : []));

      // (3) capture the charts on the hidden stage, then take it down again.
      const charts = await new Promise<Partial<Record<ChartId, ChartImage>>>((resolve, reject) => {
        pending.current = { resolve, reject };
        setStage({ input, wanted });
      }).finally(() => { pending.current = null; setStage(null); });

      // (4) libraries are only loaded now.
      const { renderReportPdf } = await import("@/lib/exportReport");
      const blob = await renderReportPdf(model, charts);
      // (5)
      download(blob, model.meta.fileName);
    } catch (e) {
      console.error("Export report failed", e);
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setPhase("idle");
    }
  }

  const busy = phase === "preparing";
  return (
    <div className="flex items-center gap-2">
      {error && (
        <span role="alert" title={error} className="max-w-[260px] truncate text-xs font-mono text-red-500">
          Export failed: {error}
        </span>
      )}
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || busy}
        title={disabled && disabledReason ? disabledReason : "Download a PDF report of Brand Equity, Risk Center and Executive Analytics"}
        className={`flex items-center gap-1.5 whitespace-nowrap px-3 py-1.5 text-xs font-mono disabled:opacity-50 disabled:cursor-not-allowed ${glassPrimaryButton(theme)}`}
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />}
        {busy ? "Preparing report..." : "Export Report"}
      </button>
      {stage && typeof document !== "undefined" &&
        createPortal(<ExportReportStage input={stage.input} wanted={stage.wanted} onDone={onStageDone} onError={onStageError} />, document.body)}
    </div>
  );
}
