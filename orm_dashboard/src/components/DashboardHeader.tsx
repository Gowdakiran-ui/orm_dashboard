import React from "react";
import { Terminal, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export interface DashboardHeaderProps {
  activeClientName: string;
  activeTab: string;
  currentTime: string;
  liveDegraded?: boolean;
}

export function DashboardHeader({
  activeClientName,
  activeTab,
  currentTime,
  liveDegraded = false
}: DashboardHeaderProps) {
  return (
    <header className="h-20 border-b border-[#1F2937]/30 bg-[#040812]/80 backdrop-blur-md flex items-center justify-between px-8 z-40 sticky top-0">
      <div className="flex items-center space-x-3">
        <span className="relative flex h-2 w-2">
          {!liveDegraded && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          )}
          <span className={`relative inline-flex rounded-full h-2 w-2 ${liveDegraded ? "bg-amber-500" : "bg-emerald-500"}`}></span>
        </span>
        <Terminal className="h-5 w-5 text-[#D4AF37] ml-2" />
        <h2 className="text-xs font-mono font-extrabold tracking-wider text-slate-200 uppercase">
          {activeClientName} SECURE ZONE // {activeTab.toUpperCase()}
        </h2>
      </div>

      <div className="flex items-center space-x-6 text-xs font-mono">
        <div className="flex items-center space-x-2 text-slate-400">
          <Clock className="h-4 w-4 text-[#D4AF37]" />
          <span>{currentTime}</span>
        </div>
        <div className="h-4 w-px bg-[#1F2937]" />
        {liveDegraded ? (
          <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/30">
            SIGNAL DEGRADED
          </Badge>
        ) : (
          <Badge className="bg-[#D4AF37]/10 text-[#D4AF37] border-[#D4AF37]/30">
            SECURE SESSION
          </Badge>
        )}
      </div>
    </header>
  );
}
