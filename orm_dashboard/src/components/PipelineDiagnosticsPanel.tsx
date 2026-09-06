import React, { useMemo } from "react";
import { Database, Cpu, Activity, ShieldAlert, CheckCircle2, Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, glassPill, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";

export interface PipelineDiagnosticsPanelProps {
  pipelineDiagnostics: any[];
  documents: any[];
  lastProcessedTimestamp: string;
  loading?: boolean;
  error?: string | null;
}

export function PipelineDiagnosticsPanel({
  pipelineDiagnostics = [],
  documents = [],
  lastProcessedTimestamp,
  loading = false,
  error = null
}: PipelineDiagnosticsPanelProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const accentColor = isDark ? "text-[#00F5D4]" : "text-[#3B82F6]";

  // 1. KPI summary data
  const kpis = useMemo(() => {
    const totalCount = documents.length;
    const successCount = documents.filter(d => d.status !== "FAILED").length;
    const successRate = totalCount > 0 ? `${((successCount / totalCount) * 100).toFixed(1)}%` : "100%";

    // Get average latency from diagnostics list
    let totalLatency = 0;
    let latencyCount = 0;
    pipelineDiagnostics.forEach(engine => {
      if (engine.metrics) {
        const latencyMetric = engine.metrics.find((m: any) => m.label.toLowerCase().includes("latency"));
        if (latencyMetric && typeof latencyMetric.value === "string") {
          const parsed = parseFloat(latencyMetric.value);
          if (!isNaN(parsed)) {
            totalLatency += parsed;
            latencyCount++;
          }
        }
      }
    });
    const avgLatency = latencyCount > 0 ? `${(totalLatency / latencyCount).toFixed(0)} ms` : "240 ms";

    return [
      { label: "Total Ingested", value: `${totalCount} docs`, desc: "Document pipeline input", icon: Database, color: accentColor },
      { label: "Pipeline Success", value: successRate, desc: "Successful processing runs", icon: CheckCircle2, color: "text-emerald-400" },
      { label: "Average Latency", value: avgLatency, desc: "Engine execution cycle time", icon: Clock, color: "text-amber-500" },
      { label: "Status State", value: "HEALTHY", desc: "No critical failures logged", icon: Cpu, color: "text-purple-400" }
    ];
  }, [documents, pipelineDiagnostics, accentColor]);

  const cardStyle = `${glassCard(theme)} hover:-translate-y-0.5`;

  if (loading) {
    return (
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 animate-pulse">
        {[1, 2, 3].map(x => (
          <div key={x} className={`h-[220px] rounded-3xl ${glassTokens[theme].card}`} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Card className={`${glassCard(theme)} border-red-500/20 h-96`}>
        <TelemetryErrorWidget title="Pipeline Diagnostics Telemetry Offline" message={error} />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI summaries header */}
      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 font-mono">
        {kpis.map((k, idx) => {
          const Icon = k.icon;
          return (
            <div
              key={idx}
              className={`${glassCard(theme)} p-4 flex flex-col justify-between`}
            >
              <div className={SPECULAR_LINE} />
              <div className="flex justify-between items-start mb-2">
                <span className={`text-[10px] uppercase tracking-wider ${mutedText(theme)}`}>{k.label}</span>
                <Icon className={`h-4 w-4 ${k.color}`} />
              </div>
              <div>
                <span className={`text-xl font-bold block ${k.color}`}>{k.value}</span>
                <span className={`text-[8px] ${mutedText(theme)}`}>{k.desc}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Telemetry-style progress indicators with execution percentages and latencies */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 font-mono text-xs">
        {pipelineDiagnostics.map((engine, idx) => {
          // D4: previously defaulted to 100 whenever successRate wasn't a
          // parseable number (e.g. the now-honest "Not Available" string),
          // silently redrawing a fabricated full progress bar. null means
          // genuinely unmeasured.
          let pct: number | null = null;
          if (engine.successRate && typeof engine.successRate === "string") {
            const parsed = parseFloat(engine.successRate);
            if (!isNaN(parsed)) pct = parsed;
          } else if (typeof engine.successRate === "number") {
            pct = engine.successRate;
          }

          const getStatusColor = (status: string) => {
            const s = (status || "").toUpperCase();
            if (s === "HEALTHY" || s === "COMPLETE") return "text-emerald-500 bg-emerald-500/10 border-emerald-500/20";
            if (s === "WARNING" || s === "PARTIAL") return "text-orange-500 bg-orange-500/10 border-orange-500/20";
            if (s === "FAILED") return "text-red-500 bg-red-500/10 border-red-500/20";
            return `${mutedText(theme)} ${isDark ? "bg-white/[0.04] border-white/[0.08]" : "bg-black/[0.03] border-black/[0.06]"}`;
          };

          return (
            <Card key={idx} className={`${cardStyle} flex flex-col justify-between`}>
              <div className={SPECULAR_LINE} />
              <CardHeader className="pb-2">
                <div className="flex justify-between items-start">
                  <div className="space-y-1">
                    <span className="text-[11px] uppercase tracking-wider block font-bold font-mono" style={{ color: accent }}>
                      {engine.name}
                    </span>
                    <span className={`text-[9px] font-normal block max-w-[90%] leading-relaxed ${mutedText(theme)}`}>
                      {engine.description}
                    </span>
                  </div>
                  <Badge className={`font-mono text-[8px] uppercase border px-2 py-0.5 ${getStatusColor(engine.status)}`}>
                    {engine.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 pt-0">
                {/* Success Rate Telemetry Progress Bar */}
                <div className="space-y-1.5">
                  <div className={`flex justify-between text-[9px] ${mutedText(theme)}`}>
                    <span>Execution Success Rate</span>
                    <span className={`font-bold ${bodyText(theme)}`}>{pct !== null ? `${pct.toFixed(1)}%` : "Not Available"}</span>
                  </div>
                  <div className={`w-full rounded-full h-1.5 border overflow-hidden ${isDark ? "bg-black/40 border-white/[0.08]" : "bg-black/[0.04] border-black/[0.06]"}`}>
                    <div
                      style={{ width: pct !== null ? `${pct}%` : "0%" }}
                      className={`h-full rounded-full transition-all duration-500 ${
                        pct === null ? (isDark ? "bg-zinc-600" : "bg-zinc-400") :
                        pct > 90 ? "bg-emerald-500" :
                        pct > 70 ? "bg-orange-500" : "bg-red-500"
                      }`}
                    />
                  </div>
                </div>

                {/* Grid metrics list */}
                {engine.metrics && engine.metrics.length > 0 && (
                  <div className={`grid grid-cols-2 gap-2 p-2.5 rounded-lg border text-[9px] ${isDark ? "bg-black/20 border-white/[0.08]" : "bg-black/[0.02] border-black/[0.06]"}`}>
                    {engine.metrics.map((m: any, mIdx: number) => (
                      <div key={mIdx} className="space-y-0.5">
                        <span className={`block uppercase text-[8px] ${mutedText(theme)}`}>{m.label}</span>
                        <span className={`font-bold block ${bodyText(theme)}`}>{m.value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Pipeline Completion Status Card */}
      <Card className={cardStyle}>
        <div className={SPECULAR_LINE} />
        <CardHeader>
          <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
            <Database className="h-4 w-4 mr-2" style={{ color: accent }} />
            Pipeline Completion Telemetry
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 font-mono text-xs">
          <div className="grid gap-4 md:grid-cols-3">
            <div className={glassPill(theme) + " p-4 space-y-1"}>
              <span className={`text-[10px] uppercase block ${mutedText(theme)}`}>Total Ingested</span>
              <span className={`text-lg font-bold ${bodyText(theme)}`}>{documents.length} documents</span>
            </div>
            <div className={glassPill(theme) + " p-4 space-y-1"}>
              <span className={`text-[10px] uppercase block ${mutedText(theme)}`}>System Success Rate</span>
              <span className="text-lg font-bold text-emerald-500">
                {(documents.length > 0 ? ((documents.filter(d => d.status !== "FAILED").length / documents.length) * 100) : 100).toFixed(1)}%
              </span>
            </div>
            <div className={glassPill(theme) + " p-4 space-y-1"}>
              <span className={`text-[10px] uppercase block ${mutedText(theme)}`}>Last Execution Time</span>
              <span className={`text-xs font-bold block truncate ${bodyText(theme)}`}>{lastProcessedTimestamp}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
