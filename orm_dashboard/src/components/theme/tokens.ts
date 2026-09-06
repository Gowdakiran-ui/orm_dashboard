import type { CSSProperties } from "react";
import type { Theme } from "./ThemeProvider";

/**
 * "Crystalline Glass" (light) / "Smoked Obsidian Glass" (dark) design
 * tokens.
 *
 * Light-mode revision (post-review): the original spec's `bg-[#F8F9FD]`
 * body + `bg-white/45` card was near-white-on-white -- cards had almost no
 * visible edge and the whole surface read as blown out. Deepened the body
 * to a soft cool-gray canvas, raised card opacity so it reads as a distinct
 * surface, swapped the white/70 border (invisible against a light body) for
 * a dark hairline, and gave the shadow real depth instead of a 6%-opacity
 * whisper. Dark mode is untouched -- it was already reading fine.
 */
export const glassTokens = {
  light: {
    body: "bg-[#EEF0F5]",
    text: "text-zinc-900",
    muted: "text-zinc-600",
    card: "bg-white/80 backdrop-blur-2xl border border-black/[0.07] shadow-[0_10px_30px_-8px_rgba(15,23,42,0.16),inset_0_1px_1px_1px_rgba(255,255,255,0.9)]",
    cardHover: "hover:bg-white/95 hover:border-black/[0.12]",
    primaryButton: "bg-zinc-950 text-white hover:bg-zinc-800",
    accentFrom: "#3B82F6",
    accentTo: "#8B5CF6",
    pill: "bg-white/90 border border-black/[0.08] shadow-sm",
  },
  dark: {
    body: "bg-[#070709]",
    text: "text-zinc-100",
    muted: "text-zinc-400",
    card: "bg-zinc-900/35 backdrop-blur-2xl border border-white/[0.12] shadow-[0_16px_40px_rgba(0,0,0,0.65),inset_0_1px_0_0_rgba(255,255,255,0.12)]",
    cardHover: "hover:bg-zinc-900/55 hover:border-white/[0.22]",
    primaryButton: "bg-white text-zinc-950 hover:bg-zinc-200",
    accentFrom: "#00F5D4",
    accentTo: "#7B2CBF",
    pill: "bg-zinc-900/70 border border-white/[0.08] shadow-inner",
  },
} as const;

/** Shared across both modes, per spec. */
export const SPECULAR_LINE =
  "pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent";

/** Base glass-card classes (background/blur/border/shadow + shared rounding). */
export function glassCard(theme: Theme, opts: { hover?: boolean } = {}): string {
  const t = glassTokens[theme];
  return `relative rounded-3xl ${t.card}${opts.hover !== false ? ` ${t.cardHover} transition-colors duration-300` : ""}`;
}

/** Pill/badge base style (status indicators, tags). */
export function glassPill(theme: Theme): string {
  return `rounded-full ${glassTokens[theme].pill}`;
}

/** Primary CTA button style. */
export function glassPrimaryButton(theme: Theme): string {
  return `rounded-lg font-bold transition-colors duration-200 ${glassTokens[theme].primaryButton}`;
}

/**
 * Gradient text for major headings only -- never body copy or data values.
 * The gradient itself is applied via inline style (`gradientHeadingStyle`):
 * a Tailwind arbitrary-value class built from a runtime hex string (e.g.
 * `bg-[linear-gradient(...,${accentFrom})]`) never appears as literal text
 * in source, so Tailwind's static scanner can't generate CSS for it.
 */
export const GRADIENT_HEADING_CLASS = "bg-clip-text text-transparent";

export function gradientHeadingStyle(theme: Theme): CSSProperties {
  const t = glassTokens[theme];
  return { backgroundImage: `linear-gradient(90deg, ${t.accentFrom}, ${t.accentTo})` };
}

export function bodyBg(theme: Theme): string {
  return glassTokens[theme].body;
}
export function bodyText(theme: Theme): string {
  return glassTokens[theme].text;
}
export function mutedText(theme: Theme): string {
  return glassTokens[theme].muted;
}
export function accentColors(theme: Theme): { from: string; to: string } {
  return { from: glassTokens[theme].accentFrom, to: glassTokens[theme].accentTo };
}
