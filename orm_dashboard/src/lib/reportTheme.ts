// Every look-and-feel value of the exported PDF lives here. Layout code reads these tokens and holds no colours,
// sizes or margins of its own, so switching to "blue cover and headers only, white content pages" is a settings change:
// set PAGE_MODE to "light" (content pages white, cards bordered) without touching the layout code.
//
// Units: millimetres for geometry, points for type.

export const PAGE = {
  format: "a4" as const,
  orientation: "landscape" as const,
  width: 297,
  height: 210,
  margin: 12, // left, right
  headerH: 14, // band reserved for the running header
  footerH: 12, // band reserved for the running footer
  gutter: 4, // between cards
  rowGap: 4,
};

// Printable content box (between header and footer, inside the side margins).
export const CONTENT = {
  x: PAGE.margin,
  y: PAGE.headerH + 4,
  w: PAGE.width - 2 * PAGE.margin,
  bottom: PAGE.height - PAGE.footerH - 2,
  get h() { return this.bottom - this.y; },
};

// "dark": deep-blue page, white cards. "light": white page, bordered cards (headers stay blue).
export type PageMode = "dark" | "light";
export const PAGE_MODE: PageMode = "dark";

const BLUE = {
  deep: "#0A2A5E", // page background
  deeper: "#071E45", // cover band / table header
  mid: "#0E3A80",
  bright: "#2F80ED", // accent
  soft: "#DBEAFE", // pale accent fill
  ink: "#0F172A",
  muted: "#64748B",
  rule: "#E2E8F0",
};

// Same meaning as the dashboard: red / orange / yellow / green (alert and score colours as in the dashboard).
export const SEVERITY = {
  CRITICAL: { solid: "#DC2626", tint: "#FCA5A5", pale: "#FEE2E2" },
  HIGH: { solid: "#EA580C", tint: "#FDBA74", pale: "#FFEDD5" },
  MEDIUM: { solid: "#CA8A04", tint: "#FDE68A", pale: "#FEF9C3" },
  LOW: { solid: "#10B981", tint: "#BBF7D0", pale: "#DCFCE7" },
} as const;

export const SENTIMENT_COLORS = { positive: "#10B981", neutral: "#64748B", negative: "#EF4444" } as const;

export const THEME = {
  blue: BLUE,
  page: {
    background: PAGE_MODE === "dark" ? BLUE.deep : "#FFFFFF",
    headerBand: PAGE_MODE === "dark" ? null : BLUE.deep, // light mode draws a blue header band
    headerInk: "#FFFFFF",
    headerMuted: "#BFD6FF",
    rule: "#2D4F8F",
    footerInk: PAGE_MODE === "dark" ? "#BFD6FF" : BLUE.muted,
  },
  card: {
    fill: "#FFFFFF",
    border: PAGE_MODE === "dark" ? null : "#CBD5E1",
    radius: 2.5,
    pad: 4,
  },
  // Neutral greys used inside cards (empty cells, empty-state panels, dim zeros, secondary chart text).
  neutral: { panel: "#F8FAFC", cell: "#F1F5F9", dim: "#94A3B8", strong: "#334155", label: "#64748B", white: "#FFFFFF", negative: "#EF4444" },
  ink: BLUE.ink,
  muted: BLUE.muted,
  accent: BLUE.bright,
  rule: BLUE.rule,
  cover: { background: BLUE.deeper, band: BLUE.mid, accent: BLUE.bright, ink: "#FFFFFF", muted: "#BFD6FF" },
  chart: {
    series: [BLUE.bright, "#0E3A80", "#60A5FA", "#93C5FD", "#1E40AF", "#38BDF8", "#818CF8", "#A5B4FC", "#0EA5E9"],
    grid: "#E2E8F0",
    axis: "#475569",
    line: BLUE.bright,
  },
  table: { headFill: BLUE.deeper, headInk: "#FFFFFF", zebra: "#F8FAFC", line: "#E2E8F0" },
  // Type scale (pt). Hierarchy comes from size, weight and colour; one family (Noto Sans Regular + Bold).
  type: { cover: 34, coverTitle: 16, h1: 15, h2: 10.5, kpi: 20, kpiLabel: 7.5, body: 8.5, small: 7.5, tiny: 6.5, table: 7.5 },
  lineHeight: 1.32,
};

export const FONT_FAMILY = "NotoSans";
export const FONT_FILES = { regular: "/fonts/NotoSans-Regular.ttf", bold: "/fonts/NotoSans-Bold.ttf" } as const;

// A page is "well filled" when at least this share of the printable height is used (the last page is exempt).
export const MIN_FILL = 0.7;
