import React from "react";
import { Sparkles, Sliders } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";

export interface AIAdvisorPanelProps {
  adviceLoading: boolean;
  adviceError: string | null;
  reputationAdvice: any;
}

export function AIAdvisorPanel({
  adviceLoading,
  adviceError,
  reputationAdvice
}: AIAdvisorPanelProps) {
  if (adviceLoading) {
    return (
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 h-[380px] animate-pulse">
        <CardHeader className="space-y-2">
          <div className="h-4 bg-[#1E293B] rounded w-1/2" />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="h-12 bg-[#1E293B]/40 rounded" />
          <div className="h-20 bg-[#1E293B]/40 rounded" />
          <div className="h-20 bg-[#1E293B]/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  if (adviceError) {
    return (
      <Card className="bg-[#060B18]/60 border-red-500/20 h-[380px]">
        <TelemetryErrorWidget title="AI Advisor Offline" message={adviceError} />
      </Card>
    );
  }

  return (
    <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl overflow-hidden hover:border-[#D4AF37]/30 transition-all duration-300">
      <div className="bg-gradient-to-r from-[#D4AF37]/10 to-transparent p-4 border-b border-[#1F2937]/40 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Sparkles className="h-5 w-5 text-[#D4AF37] animate-pulse" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-slate-200 uppercase">AI Strategic Advisory</h3>
        </div>
        <Badge className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30 font-mono text-[9px]">BRIEFING ENGINE</Badge>
      </div>
      <CardContent className="p-6 space-y-6 text-sm h-[320px] overflow-y-auto">
        {reputationAdvice ? (
          <div className="space-y-6">
            <div className="space-y-2">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">Executive Summary</span>
              <p className="text-slate-300 leading-relaxed text-xs font-mono">{reputationAdvice.executive_summary}</p>
            </div>
            <div className="space-y-2 border-t border-[#1F2937]/40 pt-4">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">Current Assessment</span>
              <p className="text-slate-300 leading-relaxed text-xs font-mono">{reputationAdvice.current_assessment}</p>
            </div>
            <div className="space-y-3 border-t border-[#1F2937]/40 pt-4">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">Priority Actions (24h)</span>
              <div className="space-y-2">
                {reputationAdvice.priority_actions_24h?.map((act: string, idx: number) => (
                  <div key={idx} className="bg-[#030712] p-3 rounded border border-[#1F2937]/40 flex items-start space-x-3">
                    <span className="h-5 w-5 rounded-full bg-[#D4AF37]/10 border border-[#D4AF37]/30 text-[#D4AF37] flex items-center justify-center text-[10px] font-mono font-bold shrink-0">{idx + 1}</span>
                    <span className="text-xs font-mono text-slate-300">{act}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex items-center space-x-2 text-[9px] font-mono text-slate-500 pt-4 border-t border-[#1F2937]/20">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#D4AF37] opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[#D4AF37]"></span>
              </span>
              <span>ENGINE ACTIVE: GROQ-LLAMA3-70B-INFERENCE</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 font-mono text-xs">
            <Sliders className="h-8 w-8 text-[#D4AF37] opacity-40 mb-3 animate-pulse" />
            No executive briefing generated.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
