import React from "react";

export interface AnalyticsTabHeaderProps {
  analyticsSubTab: string;
  onSelectSubTab: (subTab: string) => void;
}

export function AnalyticsTabHeader({
  analyticsSubTab,
  onSelectSubTab
}: AnalyticsTabHeaderProps) {
  return (
    <div className="flex space-x-6 border-b border-[#1F2937]/30 pb-0 mb-4">
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
                ? "text-[#D4AF37] font-bold border-b-2 border-[#D4AF37]" 
                : "text-slate-450 hover:text-slate-200"
            }`}
          >
            {sub.label}
          </button>
        );
      })}
    </div>
  );
}
