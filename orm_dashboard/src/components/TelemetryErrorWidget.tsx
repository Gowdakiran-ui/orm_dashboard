import React from "react";
import { AlertTriangle } from "lucide-react";

export function TelemetryErrorWidget({ title, message }: { title: string, message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[200px] text-center p-6 bg-[#060B18]/40 border border-red-500/20 rounded-lg">
      <AlertTriangle className="h-8 w-8 text-red-500/60 mb-3 animate-pulse" />
      <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">{title}</span>
      {message && <span className="text-[10px] font-mono text-slate-500 mt-2">{message}</span>}
    </div>
  );
}