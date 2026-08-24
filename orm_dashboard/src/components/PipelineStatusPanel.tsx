import React from "react";
import { Activity } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";

export interface PipelineStatusPanelProps {
  // Renamed from breakdownLoading/breakdownError -- this panel renders
  // engineDiagnosticsList, which is derived from documents/telemetry/alerts/
  // narratives/etc (see useAnalytics.ts), not from the reputation breakdown
  // fetch. The old names gated on the wrong fetch's state (FINDINGS.md #30).
  loading: boolean;
  error: string | null;
  engineDiagnosticsList: any[];
}

export function PipelineStatusPanel({
  loading,
  error,
  engineDiagnosticsList
}: PipelineStatusPanelProps) {
  if (loading) {
    return (
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 col-span-4 h-96 animate-pulse">
        <CardHeader className="space-y-2">
          <div className="h-4 bg-[#1E293B] rounded w-1/2" />
          <div className="h-3 bg-[#1E293B] rounded w-1/3" />
        </CardHeader>
        <CardContent className="space-y-4">
          {[1, 2, 3, 4, 5].map(x => (
            <div key={x} className="space-y-2">
              <div className="h-3 bg-[#1E293B] rounded w-1/4" />
              <div className="h-2 bg-[#1E293B] rounded w-full" />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="bg-[#060B18]/60 border-red-500/20 col-span-4 h-96">
        <TelemetryErrorWidget title="Pipeline Telemetry Offline" message={error} />
      </Card>
    );
  }

  return (
    <Card className="bg-[#060B18]/60 border-[#1F2937]/60 col-span-4 shadow-2xl overflow-hidden hover:border-[#D4AF37]/30 transition-all duration-300">
      <CardHeader>
        <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
          <Activity className="h-4 w-4 text-[#D4AF37] mr-2" />
          AI INTELLIGENCE PROCESSING PIPELINE
        </CardTitle>
        <CardDescription className="text-[10px] font-mono text-slate-500">Real-time status of 10 intelligence engines</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-2 max-h-[600px] overflow-y-auto">
        {engineDiagnosticsList.map((engine, idx) => (
          <div key={idx} className="space-y-1.5 group border-b border-[#1F2937]/30 pb-3 last:border-0 last:pb-0">
            <div className="flex justify-between items-center text-xs font-mono">
              <span className="text-slate-300 font-bold">{engine.name}</span>
              <Badge className={`font-mono text-[8px] ${
                engine.status === "HEALTHY" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" :
                engine.status === "NO FINDINGS" ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                "bg-slate-500/10 text-slate-300 border-slate-500/20"
              }`}>
                {engine.status}
              </Badge>
            </div>
            <div className="space-y-1 pl-2 border-l border-[#D4AF37]/20 text-[10px] font-mono">
              {engine.metrics && engine.metrics.map((metric: any, mIdx: number) => (
                <div key={mIdx} className="flex justify-between">
                  <span className="text-slate-500">{metric.label}:</span>
                  <span className="text-slate-300">{metric.value !== undefined && metric.value !== null ? metric.value : "N/A"}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
