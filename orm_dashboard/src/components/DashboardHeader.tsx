import React from "react";
import { Terminal, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassPill, mutedText } from "@/components/theme/tokens";

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
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";

  return (
    <header className={`h-20 border-b backdrop-blur-2xl flex items-center justify-between px-8 z-40 sticky top-0 ${isDark ? "border-white/[0.12] bg-zinc-900/50" : "border-black/[0.06] bg-white/50"}`}>
      <div className="flex items-center space-x-3">
        <span className="relative flex h-2 w-2">
          {!liveDegraded && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          )}
          <span className={`relative inline-flex rounded-full h-2 w-2 ${liveDegraded ? "bg-amber-500" : "bg-emerald-500"}`}></span>
        </span>
        <Terminal className="h-5 w-5 ml-2" style={{ color: accent }} />
        <h2 className={`text-xs font-mono font-extrabold tracking-wider uppercase ${isDark ? "text-zinc-200" : "text-zinc-800"}`}>
          {activeClientName} — {activeTab.toUpperCase()}
        </h2>
      </div>

      <div className="flex items-center space-x-6 text-xs font-mono">
        <div className={`flex items-center space-x-2 ${mutedText(theme)}`}>
          <Clock className="h-4 w-4" style={{ color: accent }} />
          <span>{currentTime}</span>
        </div>
        <div className={`h-4 w-px ${isDark ? "bg-white/[0.12]" : "bg-black/[0.08]"}`} />
        {liveDegraded ? (
          <Badge className={`${glassPill(theme)} text-amber-500 border-amber-500/30`}>
            SIGNAL DEGRADED
          </Badge>
        ) : (
          <Badge className={glassPill(theme)} style={{ color: accent }}>
            Connected
          </Badge>
        )}
      </div>
    </header>
  );
}
