import React from "react";
import { ShieldAlert, Shield } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";

export interface CrisisPlannerPanelProps {
  crisisLoading: boolean;
  crisisError: string | null;
  crisisPlan: any;
}

export function CrisisPlannerPanel({
  crisisLoading,
  crisisError,
  crisisPlan
}: CrisisPlannerPanelProps) {
  if (crisisLoading) {
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

  if (crisisError) {
    return (
      <Card className="bg-[#060B18]/60 border-red-500/20 h-[380px]">
        <TelemetryErrorWidget title="AI Crisis Engine Offline" message={crisisError} />
      </Card>
    );
  }

  return (
    <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl overflow-hidden hover:border-red-500/30 transition-all duration-300">
      <div className="bg-gradient-to-r from-red-500/10 to-transparent p-4 border-b border-[#1F2937]/40 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <ShieldAlert className="h-5 w-5 text-red-500" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-slate-200 uppercase">AI Crisis Command Center</h3>
        </div>
        <Badge className="bg-red-600 text-white font-mono text-[9px] font-bold">CRISIS PLANNER</Badge>
      </div>
      <CardContent className="p-6 space-y-6 text-sm h-[320px] overflow-y-auto">
        {crisisPlan ? (
          <div className="space-y-6">
            <div className="flex justify-between items-center bg-[#030712] p-3 rounded border border-[#1F2937]/40">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">CRISIS SEVERITY LEVEL:</span>
              <Badge className={`${
                crisisPlan.severity === "CRITICAL" ? "bg-red-500 text-white" :
                crisisPlan.severity === "HIGH" ? "bg-orange-500 text-white" :
                "bg-emerald-500 text-white"
              } font-mono text-xs font-bold px-2.5`}>
                {crisisPlan.severity}
              </Badge>
            </div>
            <div className="space-y-2">
              <span className="text-[10px] font-mono uppercase tracking-wider text-red-400 block">Threat Assessment</span>
              <p className="text-slate-300 leading-relaxed text-xs font-mono">{crisisPlan.executive_summary}</p>
            </div>
            <div className="space-y-3 border-t border-[#1F2937]/40 pt-4">
              <span className="text-[10px] font-mono uppercase tracking-wider text-red-400 block">Immediate Containment Actions (24h)</span>
              <div className="space-y-2">
                {crisisPlan.immediate_actions_24h?.map((act: any, idx: number) => (
                  <div key={idx} className="bg-[#030712] p-3 rounded border border-red-500/20 flex flex-col space-y-1">
                    <span className="text-xs font-mono font-bold text-slate-200">{act.action}</span>
                    <span className="text-[10px] font-mono text-slate-400 leading-normal">{act.evidence_backing}</span>
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
            <div className="flex items-center space-x-2 text-[9px] font-mono text-slate-500 pt-4 border-t border-[#1F2937]/20">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-red-500"></span>
              </span>
              <span>ENGINE ACTIVE: GROQ-LLAMA3-70B-CRISIS-MATRIX</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-emerald-500 font-mono text-xs">
            <Shield className="h-8 w-8 text-emerald-500 opacity-60 mb-3" />
            SYSTEM STATUS: SECURED. NO CRISIS SIGNAL DETECTED.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
