"use client";

import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";
import { useTheme } from "@/components/theme/ThemeProvider";

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

const PANEL_WIDTH = 256; // matches w-64
const VIEWPORT_MARGIN = 8;

/**
 * Always-visible (i) affordance that reveals `children` on hover (desktop)
 * or tap (touch devices have no hover state, so tap toggles it open/closed
 * too). The icon itself is small, but the clickable/tappable area is padded
 * out to a 44x44px minimum, matching the `touchTarget` convention already
 * used elsewhere in this dashboard (e.g. ExecutivesTab.tsx's action buttons).
 *
 * The panel is rendered in a portal straight to document.body and
 * positioned with `fixed` + getBoundingClientRect, not `absolute` inside
 * the trigger. Every card in this dashboard (ui/card.tsx) has
 * `overflow-hidden` baked in for its rounded corners -- an absolutely
 * positioned popover nested inside one gets clipped/cramped to the card's
 * own box no matter how high its z-index is (confirmed live: reported as
 * "the (i) button's data is loading inside the card, can't read it").
 * Escaping to a portal is the only way out of that clipping short of
 * stripping overflow-hidden off every card, which is a much bigger,
 * riskier change for a shared primitive used everywhere.
 *
 * Because the panel is portaled to document.body -- outside the
 * `data-theme` div the rest of the dashboard scopes its dash-* CSS
 * classes under -- it can't rely on that descendant-selector CSS (it
 * wouldn't match; portaled content isn't a DOM descendant of that div).
 * It reads `useTheme()` directly instead and mirrors the exact dash-box/
 * dash-border/dash-muted/dash-strong colors (globals.css) with
 * theme-conditional classes, the same isDark-ternary convention already
 * used throughout this codebase (e.g. RiskTab.tsx, ExecutivesTab.tsx).
 */
export function InfoTooltip({
  label = "More information",
  children,
  className = "",
  panelClassName = "",
  align = "center",
}: InfoTooltipProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number; flip: boolean } | null>(null);
  const rootRef = useRef<HTMLSpanElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const updatePosition = () => {
    const btn = btnRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();

    let left =
      align === "left"
        ? rect.left
        : align === "right"
        ? rect.right - PANEL_WIDTH
        : rect.left + rect.width / 2 - PANEL_WIDTH / 2;
    left = Math.max(VIEWPORT_MARGIN, Math.min(left, window.innerWidth - PANEL_WIDTH - VIEWPORT_MARGIN));

    // Prefer opening above the trigger; flip below it if there isn't
    // enough room near the top of the viewport (e.g. a tooltip on the
    // first card in a scrolled-to-top page).
    const flip = rect.top < 220;
    const top = flip ? rect.bottom + VIEWPORT_MARGIN : rect.top - VIEWPORT_MARGIN;

    setCoords({ top, left, flip });
  };

  useLayoutEffect(() => {
    if (open) updatePosition();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onOutside(e: MouseEvent | TouchEvent) {
      const target = e.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    function onViewportChange() {
      updatePosition();
    }
    document.addEventListener("mousedown", onOutside);
    document.addEventListener("touchstart", onOutside);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("scroll", onViewportChange, true);
    window.addEventListener("resize", onViewportChange);
    return () => {
      document.removeEventListener("mousedown", onOutside);
      document.removeEventListener("touchstart", onOutside);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", onViewportChange, true);
      window.removeEventListener("resize", onViewportChange);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const boxBg = isDark ? "bg-zinc-950/95" : "bg-white/95";
  const boxBorder = isDark ? "border-white/[0.12]" : "border-black/[0.06]";
  const strongText = isDark ? "text-zinc-100" : "text-zinc-900";

  return (
    <span ref={rootRef} className={`relative inline-flex ${className}`}>
      <button
        ref={btnRef}
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
        className={`relative inline-flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center rounded-full hover:opacity-75 focus:opacity-75 focus:outline-none ${
          isDark ? "text-zinc-400" : "text-zinc-600"
        }`}
      >
        <Info className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      {open &&
        coords &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={panelRef}
            id={panelId}
            role="tooltip"
            style={{
              position: "fixed",
              top: coords.top,
              left: coords.left,
              transform: coords.flip ? undefined : "translateY(-100%)",
            }}
            className={`z-[9999] w-64 max-w-[80vw] space-y-1 rounded-xl border ${boxBg} ${boxBorder} p-3 text-left text-xs font-mono leading-relaxed shadow-2xl ${panelClassName}`}
          >
            <span className={`block ${strongText}`}>{children}</span>
          </div>,
          document.body
        )}
    </span>
  );
}
