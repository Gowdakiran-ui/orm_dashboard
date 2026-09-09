"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import { Info } from "lucide-react";

export interface InfoTooltipProps {
  /** Accessible name for the trigger icon (screen readers, not shown visually). */
  label?: string;
  /**
   * Tooltip content. Static text/JSX for Tier 1 (this task); Tier 3 can pass
   * a component that fetches its own data, a loading state, or any other
   * dynamic ReactNode here without changing this component.
   */
  children: React.ReactNode;
  /** Extra classes on the trigger wrapper (e.g. to nudge spacing next to a label). */
  className?: string;
  /** Extra classes on the popover panel. */
  panelClassName?: string;
  /** Horizontal anchor of the popover relative to the trigger. */
  align?: "left" | "center" | "right";
}

/**
 * Always-visible (i) affordance that reveals `children` on hover (desktop)
 * or tap (touch devices have no hover state, so tap toggles it open/closed
 * too). The icon itself is small, but the clickable/tappable area is padded
 * out to a 44x44px minimum, matching the `touchTarget` convention already
 * used elsewhere in this dashboard (e.g. ExecutivesTab.tsx's action buttons).
 * Colors come from the dash-* theme classes (globals.css) so this is
 * light/dark-safe without any theme-conditional logic here.
 */
export function InfoTooltip({
  label = "More information",
  children,
  className = "",
  panelClassName = "",
  align = "center",
}: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    function onOutside(e: MouseEvent | TouchEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onOutside);
    document.addEventListener("touchstart", onOutside);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onOutside);
      document.removeEventListener("touchstart", onOutside);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const alignClass =
    align === "left" ? "left-0" : align === "right" ? "right-0" : "left-1/2 -translate-x-1/2";

  return (
    <span ref={rootRef} className={`relative inline-flex ${className}`}>
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-describedby={panelId}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="relative inline-flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center rounded-full dash-muted hover:opacity-75 focus:opacity-75 focus:outline-none"
      >
        <Info className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      {open && (
        <span
          id={panelId}
          role="tooltip"
          className={`dash-box dash-border absolute bottom-full z-50 mb-2 w-64 max-w-[80vw] space-y-1 rounded-xl border p-3 text-left text-xs font-mono leading-relaxed shadow-2xl ${alignClass} ${panelClassName}`}
        >
          <span className="dash-strong block">{children}</span>
        </span>
      )}
    </span>
  );
}
