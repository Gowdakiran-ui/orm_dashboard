import React from "react";
import { Award } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";

export interface ReputationCardProps {
  reputationLoading: boolean;
  reputationError: string | null;
  reputation: any;
}

export function ReputationCard({
  reputationLoading,
  reputationError,
  reputation
}: ReputationCardProps) {
  if (reputationLoading) {
    return (
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 col-span-3 h-96 flex flex-col justify-between animate-pulse">
        <CardHeader className="space-y-2">
          <div className="h-4 bg-[#1E293B] rounded w-1/3" />
          <div className="h-3 bg-[#1E293B] rounded w-1/4" />
        </CardHeader>
        <CardContent className="flex flex-col items-center justify-center pb-8">
          <div className="h-40 w-40 rounded-full border-4 border-[#1E293B] flex items-center justify-center">
            <div className="h-32 w-32 rounded-full bg-[#1E293B]/50" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (reputationError) {
    return (
      <Card className="bg-[#060B18]/60 border-red-500/20 col-span-3 h-96">
        <TelemetryErrorWidget title="Radar Telemetry Offline" message={reputationError} />
      </Card>
    );
  }

  return (
    <Card className="bg-[#060B18]/60 border-[#1F2937]/60 col-span-3 shadow-2xl flex flex-col justify-between overflow-hidden relative group hover:border-[#D4AF37]/30 transition-all duration-300">
      <div className="absolute top-0 right-0 p-4">
        <Award className="h-5 w-5 text-[#D4AF37] opacity-60" />
      </div>
      <CardHeader>
        <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Tactical Reputation Radar</CardTitle>
        <CardDescription className="text-[10px] font-mono text-[#D4AF37]">Overall Brand Equity Metric</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col items-center justify-center py-6">
        <div className="relative flex items-center justify-center">
          <svg className="w-48 h-48 transform -rotate-90">
            <circle cx="96" cy="96" r="80" stroke="#0E1626" strokeWidth="6" fill="transparent" />
            <circle 
              cx="96" cy="96" r="80" 
              stroke="#D4AF37" strokeWidth="6" fill="transparent" 
              strokeDasharray={2 * Math.PI * 80}
              strokeDashoffset={2 * Math.PI * 80 * (1 - (reputation?.score || 0) / 100)}
              strokeLinecap="round"
              className="drop-shadow-[0_0_15px_rgba(212,175,55,0.4)]"
            />
          </svg>
          <div className="absolute flex flex-col items-center justify-center">
            <span className="text-5xl font-mono font-black text-slate-100">
              {reputation?.score ? reputation.score.toFixed(1) : '0.0'}
            </span>
            <span className="text-xs font-mono text-[#D4AF37] mt-1 tracking-widest">
              GRADE {reputation?.grade ?? 'N/A'}
            </span>
          </div>
        </div>
        <div className="mt-6 flex items-center space-x-3 text-xs font-mono text-slate-300">
          <span>TREND DIRECTION:</span>
          <Badge className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30">
            {reputation?.trend ?? 'STABLE'}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}
