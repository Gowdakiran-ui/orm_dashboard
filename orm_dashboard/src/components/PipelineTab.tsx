import React from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Activity, ArrowRight } from "lucide-react";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassPill, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";

export interface PipelineTabProps {
  commandStats: any;
  documents: any[];
  trendEvents: any[];
  alerts: any[];
  narratives: any[];
  repHistory: any[];
  executives: any[];
  benchmarks: any[];
  engineDiagnosticsList: any[];
  onSelectTab: (tab: string) => void;
}

export function PipelineTab({
  commandStats,
  documents,
  trendEvents,
  alerts,
  narratives,
  repHistory,
  executives,
  benchmarks,
  engineDiagnosticsList,
  onSelectTab
}: PipelineTabProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";

  return (
    <div className="space-y-8">

      {/* 1. Ingestion Flow Graph */}
      <Card className={`${glassCard(theme)} overflow-hidden`}>
        <div className={SPECULAR_LINE} />
        <CardHeader>
          <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
            <Activity className="h-4 w-4 mr-2" style={{ color: accent }} />
            AI Intelligence Processing Pipeline Flow
          </CardTitle>
          <CardDescription className={`text-[10px] font-mono ${mutedText(theme)}`}>
            Live data flow mapping: from raw unstructured document collection to C-Suite brand intelligence insights.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-6">
          <div className={`flex flex-wrap items-center justify-center gap-4 p-6 rounded-2xl border ${isDark ? "bg-black/20 border-white/[0.08]" : "bg-black/[0.02] border-black/[0.06]"}`}>
            {[
              { name: "Collection", count: (commandStats?.docs_today !== undefined && commandStats?.docs_today !== null) ? commandStats.docs_today : "Not Available", label: "Feeds" },
              { name: "Documents", count: documents.length, label: "Ingested" },
              { name: "Entity Matching", count: documents.length, label: "Resolved" },
              { name: "Topic Classifier", count: new Set(documents.map(d => d.topic).filter(Boolean)).size, label: "Topics" },
              { name: "Sentiment Analyzer", count: documents.filter(d => d.sentiment !== undefined).length, label: "Scores" },
              { name: "Trend Detection", count: trendEvents.length, label: "Trends" },
              { name: "Risk Engine", count: documents.filter(d => d.risk > 0).length, label: "Threats" },
              { name: "Alert Engine", count: alerts.length, label: "Alerts" },
              { name: "Narrative Engine", count: narratives.length, label: "Clusters" },
              { name: "Reputation Engine", count: repHistory.length, label: "Equity Index" },
              { name: "Executive Reputation", count: executives.length, label: "Tracked" },
              { name: "Benchmark Engine", count: benchmarks.length, label: "Competitors" }
            ].map((step, idx, arr) => (
              <React.Fragment key={idx}>
                <div className={glassPill(theme) + " p-3 min-w-[120px] text-center font-mono rounded-lg"}>
                  <span className={`text-[8px] uppercase block ${mutedText(theme)}`}>{step.name}</span>
                  <span className={`text-sm font-bold block my-1 ${bodyText(theme)}`}>{step.count}</span>
                  <span className="text-[8px] uppercase tracking-wider" style={{ color: accent }}>{step.label}</span>
                </div>
                {idx < arr.length - 1 && (
                  <ArrowRight className={`h-4 w-4 hidden md:block ${mutedText(theme)}`} />
                )}
              </React.Fragment>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 2. 10 Production Engine Cards */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {engineDiagnosticsList.map((engine, idx) => (
          <Card key={idx} className={`${glassCard(theme)} flex flex-col justify-between`}>
            <div className={SPECULAR_LINE} />
            <div>
              <CardHeader className="pb-3">
                <div className="flex justify-between items-center">
                  <CardTitle className={`text-xs font-mono uppercase tracking-wider ${bodyText(theme)}`}>{engine.name}</CardTitle>
                  <Badge className={`font-mono text-[9px] ${
                    engine.status === "HEALTHY" ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/30" :
                    engine.status === "NO FINDINGS" ? "bg-blue-500/10 text-blue-500 border-blue-500/30" :
                    engine.status === "WARNING" ? "bg-orange-500/10 text-orange-500 border-orange-500/30" :
                    `${mutedText(theme)} ${isDark ? "bg-white/[0.04] border-white/[0.12]" : "bg-black/[0.03] border-black/[0.08]"}`
                  }`}>
                    {engine.status}
                  </Badge>
                </div>
                <CardDescription className={`text-[10px] font-mono leading-relaxed mt-1 ${mutedText(theme)}`}>
                  {engine.description}
                </CardDescription>
              </CardHeader>
              <CardContent className={`space-y-2 border-t pt-3 font-mono text-[10px] ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                {engine.metrics && engine.metrics.length > 0 ? (
                  engine.metrics.map((metric: any, idx: number) => (
                    <div key={idx} className="flex justify-between">
                      <span className={mutedText(theme)}>{metric.label}:</span>
                      <span className={bodyText(theme)}>{metric.value}</span>
                    </div>
                  ))
                ) : (
                  <>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Processed Inputs:</span>
                      <span className={bodyText(theme)}>{engine.processed} docs</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Outputs Generated:</span>
                      <span className={bodyText(theme)}>{engine.produced} records</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Execution Success Rate:</span>
                      <span className={bodyText(theme)}>{engine.successRate}</span>
                    </div>
                  </>
                )}
                {(engine.failed !== undefined && engine.failed !== null && engine.failed > 0) && (
                  <div className="flex justify-between">
                    <span className="text-red-500">Failed Count:</span>
                    <span className="text-red-500 font-bold">{engine.failed} docs</span>
                  </div>
                )}
              </CardContent>
            </div>
            <div className={`p-4 border-t flex justify-end ${isDark ? "border-white/[0.08] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
              <button
                onClick={() => onSelectTab(engine.navigationId)}
                className="font-mono text-[9px] hover:underline"
                style={{ color: accent }}
              >
                OPEN SUB-MODULE TELEMETRY &rarr;
              </button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
