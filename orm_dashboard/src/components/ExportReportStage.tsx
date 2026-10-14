"use client";

// The hidden stage the Export Report button mounts on click. It renders the real Executive Analytics panels, with the
// SNAPSHOT taken at click time (never live hook values), in a fixed-size container off-screen and always in the light
// theme, so the charts can be captured for the PDF exactly as the screen draws them. It makes no network calls and the
// button unmounts it as soon as the capture finishes.
import React, { useEffect, useRef } from "react";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { OverviewAnalyticsPanel } from "@/components/OverviewAnalyticsPanel";
import { RiskAnalyticsPanel } from "@/components/RiskAnalyticsPanel";
import { captureCharts, type WantedChart } from "@/lib/captureCharts";
import type { ReportInput, ChartId } from "@/utils/reportModel";
import type { ChartImage } from "@/lib/exportReport";

// Narrow enough that each chart is drawn about 520px wide, which keeps its labels legible once scaled onto A4.
export const STAGE_WIDTH = 560;

export interface ExportReportStageProps {
  input: ReportInput;
  wanted: WantedChart[];
  onDone: (charts: Partial<Record<ChartId, ChartImage>>) => void;
  onError: (e: Error) => void;
}

export function ExportReportStage({ input, wanted, onDone, onError }: ExportReportStageProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current || !ref.current) return;
    started.current = true;
    if (wanted.length === 0) { onDone({}); return; }
    captureCharts(ref.current, wanted).then(onDone, e => onError(e instanceof Error ? e : new Error(String(e))));
  }, [wanted, onDone, onError]);

  const a = input.analytics;
  return (
    <ThemeProvider forcedTheme="light">
      <div
        ref={ref}
        aria-hidden="true"
        data-report-stage="true"
        // Off-screen but laid out (not display:none), fixed width so the charts have a real size.
        style={{ position: "fixed", left: -20000, top: 0, width: STAGE_WIDTH, pointerEvents: "none", background: "#ffffff" }}
      >
        {/* The panels lay their cards out by viewport width (md:/lg: grids). On the stage every card is one column, whatever the screen. */}
        <style>{`[data-report-stage] [class*="grid-cols-"] { display: block !important; } [data-report-stage] [class*="grid-cols-"] > * { margin-bottom: 16px; }`}</style>
        <OverviewAnalyticsPanel
          reputation={input.reputationSummary?.reputation}
          sentimentDistData={a.sentimentDistData}
          topicDistData={a.topicDistData}
          repHistory={input.repHistory}
          sentimentHistoryData={[]}
          animate={false}
        />
        <RiskAnalyticsPanel
          riskMatrixData={a.riskMatrixData}
          reputationSummary={input.reputationSummary}
          reputationSummaryLoading={false}
          reputationSummaryError={input.reputationSummaryError}
          alertSeverityData={[]}
          riskHeatmapData={a.riskHeatmapData}
          alertTimelineData={a.alertTimelineData}
          animate={false}
        />
      </div>
    </ThemeProvider>
  );
}
