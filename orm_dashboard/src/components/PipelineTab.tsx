import React from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Activity, ArrowRight } from "lucide-react";

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
  return (
    <div className="space-y-8">
      
      {/* 1. Ingestion Flow Graph */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl overflow-hidden">
        <CardHeader>
          <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
            <Activity className="h-4 w-4 text-[#D4AF37] mr-2" />
            AI Intelligence Processing Pipeline Flow
          </CardTitle>
          <CardDescription className="text-[10px] font-mono text-slate-500">
            Live data flow mapping: from raw unstructured document collection to C-Suite brand intelligence insights.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-6">
          <div className="flex flex-wrap items-center justify-center gap-4 bg-[#030712]/50 p-6 rounded-lg border border-[#1F2937]/20">
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
                <div className="bg-[#060B18] border border-[#1F2937]/60 rounded p-3 min-w-[120px] text-center font-mono">
                  <span className="text-[8px] text-slate-500 uppercase block">{step.name}</span>
                  <span className="text-sm font-bold text-slate-200 block my-1">{step.count}</span>
                  <span className="text-[8px] text-[#D4AF37] uppercase tracking-wider">{step.label}</span>
                </div>
                {idx < arr.length - 1 && (
                  <ArrowRight className="h-4 w-4 text-slate-600 hidden md:block" />
                )}
              </React.Fragment>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 2. 10 Production Engine Cards */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {engineDiagnosticsList.map((engine, idx) => (
          <Card key={idx} className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl hover:border-[#D4AF37]/30 transition-all duration-300 flex flex-col justify-between">
            <div>
              <CardHeader className="pb-3">
                <div className="flex justify-between items-center">
                  <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-200">{engine.name}</CardTitle>
                  <Badge className={`font-mono text-[9px] ${
                    engine.status === "HEALTHY" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" :
                    engine.status === "NO FINDINGS" ? "bg-blue-500/10 text-blue-400 border-blue-500/30" :
                    engine.status === "WARNING" ? "bg-orange-500/10 text-orange-400 border-orange-500/30" :
                    "bg-slate-500/10 text-slate-300 border-slate-500/30"
                  }`}>
                    {engine.status}
                  </Badge>
                </div>
                <CardDescription className="text-[10px] font-mono text-slate-500 leading-relaxed mt-1">
                  {engine.description}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 border-t border-[#1F2937]/30 pt-3 font-mono text-[10px]">
                {engine.metrics && engine.metrics.length > 0 ? (
                  engine.metrics.map((metric: any, idx: number) => (
                    <div key={idx} className="flex justify-between">
                      <span className="text-slate-500">{metric.label}:</span>
                      <span className="text-slate-200">{metric.value}</span>
                    </div>
                  ))
                ) : (
                  <>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Processed Inputs:</span>
                      <span className="text-slate-200">{engine.processed} docs</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Outputs Generated:</span>
                      <span className="text-slate-200">{engine.produced} records</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Execution Success Rate:</span>
                      <span className="text-slate-200">{engine.successRate}</span>
                    </div>
                  </>
                )}
                {(engine.failed !== undefined && engine.failed !== null && engine.failed > 0) && (
                  <div className="flex justify-between">
                    <span className="text-red-400">Failed Count:</span>
                    <span className="text-red-400 font-bold">{engine.failed} docs</span>
                  </div>
                )}
              </CardContent>
            </div>
            <div className="p-4 border-t border-[#1F2937]/30 bg-[#030712]/40 flex justify-end">
              <button 
                onClick={() => onSelectTab(engine.navigationId)}
                className="font-mono text-[9px] text-[#D4AF37] hover:underline"
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
