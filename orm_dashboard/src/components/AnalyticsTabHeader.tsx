import React from "react";
import { useTheme } from "@/components/theme/ThemeProvider";
import { mutedText } from "@/components/theme/tokens";

export interface AnalyticsTabHeaderProps {
  analyticsSubTab: string;
  onSelectSubTab: (subTab: string) => void;
  isSuperAdmin?: boolean;
}

export function AnalyticsTabHeader({
  analyticsSubTab,
  onSelectSubTab,
  isSuperAdmin
}: AnalyticsTabHeaderProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";

  return (
    // Same responsive-collapse pattern as RiskTab.tsx's "At a Glance" tile
    // row (grid + sm:/md: column breakpoints) rather than a plain flex row
    // -- a flex row with no wrap just squeezes every button down to fit,
    // which is what forced these 4 labels into a 45.7px-wide vertical
    // waterfall of single words at mobile width (Responsive Layout
    // Forensics, mobile section). 2 columns below sm gives each label
    // roughly half the row instead of a quarter; md:grid-cols-4 keeps the
    // single-row layout from 768px up, where the audit already confirmed
    // there's enough room (85.6px-tall buttons, comfortable gaps).
    <div className={`grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 border-b pb-0 mb-4 ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
      {[
        { id: "overview", label: "Reputation & Sentiment Trends" },
        { id: "risk", label: "Risk & Alert Profile" }
      ].map(sub => {
        const isActive = analyticsSubTab === sub.id;
        return (
          <button
            key={sub.id}
            onClick={() => onSelectSubTab(sub.id)}
            className={`pb-3 text-xs font-mono transition-all relative text-left ${
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
