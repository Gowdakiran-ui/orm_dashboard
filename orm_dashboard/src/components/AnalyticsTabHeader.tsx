import React from "react";
import { useTheme } from "@/components/theme/ThemeProvider";
import { mutedText } from "@/components/theme/tokens";

export interface AnalyticsTabHeaderProps {
  analyticsSubTab: string;
  onSelectSubTab: (subTab: string) => void;
}

export function AnalyticsTabHeader({
  analyticsSubTab,
  onSelectSubTab
}: AnalyticsTabHeaderProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";

  return (
    <div className={`flex space-x-6 border-b pb-0 mb-4 ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
      {[
        { id: "overview", label: "Reputation & Sentiment Trends" },
        { id: "risk", label: "Risk & Alert Profile" },
        { id: "narratives", label: "Narrative & Ingestion Analytics" },
        { id: "pipeline", label: "AI Platform Diagnostics" }
      ].map(sub => {
        const isActive = analyticsSubTab === sub.id;
        return (
          <button
            key={sub.id}
            onClick={() => onSelectSubTab(sub.id)}
            className={`pb-3 text-xs font-mono transition-all relative ${
              isActive
                ? "font-bold border-b-2"
                : `${mutedText(theme)} border-b-2 border-transparent ${isDark ? "hover:text-zinc-200" : "hover:text-zinc-800"}`
            }`}
            style={isActive ? { color: accent, borderColor: accent } : undefined}
          >
            {sub.label}
          </button>
        );
      })}
    </div>
  );
}
