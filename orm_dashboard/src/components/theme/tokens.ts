import type { CSSProperties } from "react";
import type { Theme } from "./ThemeProvider";

/**
 * "Crystalline Glass" (light) / "Smoked Obsidian Glass" (dark) design
 * tokens.
 *
 * Light-mode revision 2 (opacity rebalance): revision 1 (below) fixed
 * "cards have no visible edge" by pushing card opacity to /80 -- but on a
 * data-dense screen where cards cover most of the viewport, an 80%-opaque
 * white card reads as a flat wall of white; the soft-gray body barely
 * shows through, unlike dark mode's own card (bg-zinc-900/35, 65%
 * translucent) which lets its near-black body read through for real glass
 * depth. Lowered to /60 to mirror dark mode's translucency, and moved the
 * "visible edge" job onto a stronger border + deeper shadow instead of
 * opacity, so cards stay clearly separated from the body without going
 * back to looking blown-out.
 *
 * Light-mode revision 1 (post-review): the original spec's `bg-[#F8F9FD]`
 * body + `bg-white/45` card was near-white-on-white -- cards had almost no
 * visible edge and the whole surface read as blown out. Deepened the body
 * to a soft cool-gray canvas, raised card opacity so it reads as a distinct
 * surface, swapped the white/70 border (invisible against a light body) for
 * a dark hairline, and gave the shadow real depth instead of a 6%-opacity
 * whisper. Dark mode is untouched -- it was already reading fine.
 */
export const glassTokens = {
  light: {
    body: "bg-[var(--page)]",
    text: "text-[var(--fg)]",
    muted: "text-[var(--fg-muted)]",
    card: "bg-[var(--surface)] border border-[var(--line)] shadow-[var(--shadow-card)]",
    cardHover: "hover:border-[var(--line-strong)]",
    primaryButton: "bg-[var(--brand)] text-white hover:bg-[var(--brand-hover)]",
    accentFrom: "#1D4ED8",
    accentTo: "#6D28D9",
    pill: "bg-[var(--surface)] border border-[var(--line)] shadow-sm",
  },
  dark: {
    body: "bg-[var(--page)]",
    text: "text-[var(--fg)]",
    muted: "text-[var(--fg-muted)]",
    card: "bg-[var(--surface)] border border-[var(--line)] shadow-[var(--shadow-card)]",
    cardHover: "hover:border-[var(--line-strong)]",
    primaryButton: "bg-[var(--brand)] text-[#0F1419] hover:bg-[var(--brand-hover)]",
    accentFrom: "#2DD4BF",
    accentTo: "#A78BFA",
    pill: "bg-[var(--surface-raised)] border border-[var(--line)]",
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
