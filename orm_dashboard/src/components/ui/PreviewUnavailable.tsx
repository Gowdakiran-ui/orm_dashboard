import React from "react";
import { useTheme } from "@/components/theme/ThemeProvider";

/**
 * A document/row has no real title when the backend's title fallback fired
 * (documents.py: `doc.title or "Untitled Document"`, per
 * forensics_confirmation_final.md item 17) -- confirmed live to also render
 * as the raw source name standing in for a headline (e.g. a card titled
 * literally "Instagram Search"), not only the literal string
 * "Untitled Document". Both shapes are detected here without any new
 * backend field: a title that's missing, or one that's identical to its own
 * source name, is not a real headline.
 */
export function isPlaceholderTitle(title?: string | null, source?: string | null): boolean {
  const t = (title ?? "").trim();
  if (!t) return true;
  if (t.toLowerCase() === "untitled document") return true;
  const s = (source ?? "").trim();
  if (s && t.toLowerCase() === s.toLowerCase()) return true;
  return false;
}

/**
 * Shared display-only mitigation for a title-less document/row, used
 * identically in all three places one currently renders (Narrative
 * Cluster's Source Evidence panel, Executive Reputation's activity table,
 * Intelligence Stream's Real-Time Brand Ingest Stream feed) --
 * ui_redesign_plan.md #2. Visually de-emphasized and labeled "Preview
 * unavailable" instead of showing the raw source name as if it were a real,
 * evaluated headline next to a 0.00/0 score. Does not attempt to fix why
 * the title is missing -- that's the backend/ingestion issue named above,
 * out of scope here.
 */
export function PreviewUnavailableLabel({ className = "" }: { className?: string }) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  return (
    <span className={`italic ${isDark ? "text-zinc-500" : "text-zinc-400"} ${className}`}>
      Preview unavailable
    </span>
  );
}

/** Shared de-emphasis classes for the row/card wrapper itself (smaller, muted, no hover-highlight escalation). */
export const PLACEHOLDER_ROW_CLASS = "opacity-60 saturate-[0.6]";
