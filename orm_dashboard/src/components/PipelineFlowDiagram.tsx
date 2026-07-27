import React from "react";
import { Activity, ArrowRight, CheckCircle2, XCircle, AlertCircle, Play, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function PipelineFlowDiagram({
  commandStats,
  documents,
  trendEvents,
  alerts,
  narratives,
  repHistory,
  executives,
  benchmarks,
  executiveCandidates,
  competitorCandidates,
  onNavigate
}: {
  commandStats: any,
  documents: any[],
  trendEvents: any[],
  alerts: any[],
  narratives: any[],
  repHistory: any[],
  executives: any[],
  benchmarks: any[],
  executiveCandidates: any[],
  competitorCandidates: any[],
  onNavigate: (tab: string) => void
}) {
  const steps = [
    { name: "Crawler", processed: (commandStats?.docs_today !== undefined && commandStats?.docs_today !== null) ? commandStats.docs_today : "Not Available", produced: (commandStats?.docs_today !== undefined && commandStats?.docs_today !== null) ? commandStats.docs_today : "Not Available", status: typeof commandStats?.docs_today === 'number' && commandStats.docs_today > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "Monitors RSS feeds and web sources for new content.", tab: "feed" },
    { name: "Collection", processed: (commandStats?.docs_today !== undefined && commandStats?.docs_today !== null) ? commandStats.docs_today : "Not Available", produced: (commandStats?.docs_today !== undefined && commandStats?.docs_today !== null) ? commandStats.docs_today : "Not Available", status: typeof commandStats?.docs_today === 'number' && commandStats.docs_today > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "Ingests raw text RSS feeds, crawler streams.", tab: "feed" },
    { name: "Cleaning", processed: (documents || []).length, produced: (documents || []).length, status: (documents || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "Normalizes and sanitizes raw text streams.", tab: "feed" },
    { name: "Entity Matching", processed: (documents || []).length, produced: (documents || []).length, status: (documents || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "Extracts and links key executives and brands.", tab: "executives" },
    { name: "Executive Discovery", processed: (documents || []).length, produced: (executiveCandidates || []).length, status: (documents || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "NER-based executive candidate identification.", tab: "executives" },
    { name: "Competitor Discovery", processed: (documents || []).length, produced: (competitorCandidates || []).length, status: (documents || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "NER-based competitor candidate identification.", tab: "competitors" },
    { name: "Topic Classification", processed: (documents || []).length, produced: new Set((documents || []).map(d => d?.topic).filter(Boolean)).size, status: (documents || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "Categorizes corporate topics and strategic dimensions.", tab: "analytics" },
    { name: "Sentiment Analysis", processed: (documents || []).length, produced: (documents || []).filter(d => d && d.sentiment !== undefined).length, status: (documents || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "Calculates polarity vector scores (-1..1).", tab: "analytics" },
    { name: "Trend Detection", processed: (documents || []).length, produced: (trendEvents || []).length, status: (trendEvents || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: (trendEvents || []).length > 0 ? "Identifies momentum spikes in topic mentions." : "No trend events detected. System continues monitoring.", tab: "feed" },
    { name: "Risk Engine", processed: (documents || []).length, produced: (documents || []).filter(d => d && d.risk > 0).length, status: (documents || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: (documents || []).filter(d => d && d.risk > 0).length > 0 ? "Evaluates impact and threat likelihood vectors." : "No active reputation risks detected.", tab: "risk" },
    { name: "Alert Engine", processed: (documents || []).length, produced: (alerts || []).length, status: (alerts || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: (alerts || []).length > 0 ? "Triggers notifications on threshold breaks." : "No alerts generated. All monitored thresholds remain within acceptable limits.", tab: "risk" },
    { name: "Narrative Engine", processed: (documents || []).length, produced: (narratives || []).length, status: (narratives || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: (narratives || []).length > 0 ? "Clusters topics into distinct narrative tracks." : "No dominant narrative clusters identified.", tab: "narratives" },
    { name: "Reputation Engine", processed: (documents || []).length, produced: (repHistory || []).length, status: (repHistory || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "Calculates overall brand equity scores.", tab: "reputation" },
    { name: "Executive Reputation", processed: (documents || []).length, produced: (executives || []).length, status: (executives || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: (executives || []).length > 0 ? "Tracks individual leadership profiles." : "No executive reputation history available yet.", tab: "executives" },
    { name: "Benchmark Engine", processed: (documents || []).length, produced: (benchmarks || []).length, status: (benchmarks || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: (benchmarks || []).length > 0 ? "Compares platform scores against competitors." : "Waiting for verified competitor intelligence.", tab: "competitors" },
    { name: "Dashboard", processed: (documents || []).length, produced: (documents || []).length, status: (documents || []).length > 0 ? "HEALTHY" : "NO FINDINGS", completion: "Unavailable", desc: "Renders executive intelligence to command interface.", tab: "reputation" }
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {steps.map((step, idx) => (
          <div
            key={idx}
            onClick={() => step.tab && onNavigate(step.tab)}
            className={`cursor-pointer transition-all duration-300 ${
              step.tab ? 'hover:border-[#D4AF37]/50 hover:shadow-[0_0_15px_rgba(212,175,55,0.15)]' : ''
            } bg-[#060B18] border border-[#1F2937]/60 rounded-lg p-4 relative overflow-hidden`}
          >
            {/* Animated connecting line for non-last items */}
            {idx < steps.length - 1 && (
              <div className="absolute right-0 top-1/2 w-8 h-0.5 bg-gradient-to-r from-[#1F2937] to-[#D4AF37]/30 transform translate-x-full -translate-y-1/2 hidden md:block" />
            )}
            
            {/* Status indicator */}
            <div className="flex items-center justify-between mb-2">
              <Badge className={`font-mono text-[9px] ${
                step.status === "HEALTHY" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" :
                step.status === "NO FINDINGS" ? "bg-blue-500/10 text-blue-400 border-blue-500/30" :
                "bg-slate-500/10 text-slate-300 border-slate-500/30"
              }`}>
                {step.status}
              </Badge>
              <span className="text-[8px] font-mono text-slate-500">{step.completion}</span>
            </div>
            
            {/* Stage name */}
            <div className="text-xs font-mono font-bold text-slate-200 mb-1">{step.name}</div>
            
            {/* Description */}
            <div className="text-[9px] font-mono text-slate-500 mb-3 leading-tight">{step.desc}</div>
            
            {/* Metrics */}
            <div className="flex items-center justify-between text-[8px] font-mono text-slate-400">
              <div>
                <span className="text-slate-600">Processed:</span> {step.processed}
              </div>
              <div>
                <span className="text-slate-600">Output:</span> {step.produced}
              </div>
            </div>
            
            {/* Progress bar */}
            <div className="mt-2 w-full bg-[#030712] h-1 rounded-full overflow-hidden border border-[#1F2937]/40">
              <div 
                className={`h-full rounded-full transition-all duration-1000 ease-out ${
                  step.status === "HEALTHY" ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]" :
                  step.status === "NO FINDINGS" ? "bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.4)]" :
                  "bg-slate-500"
                }`} 
                style={{ width: step.completion }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}