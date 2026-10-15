// Native vector charts for the PDF report, drawn with jsPDF primitives from the report model's data (no Recharts, no
// canvas capture). Text uses the report font through Pen, so every chart label is real PDF text.
import { Pen } from "@/lib/reportDraw";
import { SENTIMENT_COLORS, THEME } from "@/lib/reportTheme";

const AX = THEME.chart.axis;
const FS = 6.5; // axis label size (pt): legible at print size

// "Nice" tick values covering [min, max] with about `count` steps.
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!(max > min)) { max = min + 1; }
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) ?? 10 * mag;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const out: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) out.push(Math.round(v * 1000) / 1000);
  return out;
}

// ---------------------------------------------------------------- donut + legend
export function drawDonut(pen: Pen, x: number, y: number, w: number, h: number, items: { name: string; value: number }[]) {
  const d = pen.doc;
  const total = items.reduce((s, i) => s + i.value, 0);
  const colorOf = (n: string) => (SENTIMENT_COLORS as Record<string, string>)[n.toLowerCase()] ?? THEME.chart.series[0];
  const R = Math.min(h / 2, w * 0.28), r = R * 0.62;
  const cx = x + R + 2, cy = y + h / 2;
  if (total <= 0) { d.setFillColor(THEME.rule); d.circle(cx, cy, R, "F"); d.setFillColor(THEME.neutral.white); d.circle(cx, cy, r, "F"); return; }
  const shown = items.filter(i => i.value > 0);
  if (shown.length === 1) {
    d.setFillColor(colorOf(shown[0].name)); d.circle(cx, cy, R, "F");
    d.setFillColor(THEME.neutral.white); d.circle(cx, cy, r, "F");
  } else {
    let a0 = -Math.PI / 2;
    for (const it of shown) {
      const a1 = a0 + (it.value / total) * 2 * Math.PI;
      const steps = Math.max(2, Math.ceil(((a1 - a0) / (2 * Math.PI)) * 120));
      const pts: [number, number][] = [];
      for (let k = 0; k <= steps; k++) { const a = a0 + ((a1 - a0) * k) / steps; pts.push([cx + R * Math.cos(a), cy + R * Math.sin(a)]); }
      for (let k = steps; k >= 0; k--) { const a = a0 + ((a1 - a0) * k) / steps; pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]); }
      const segs = pts.slice(1).map((p, k) => [p[0] - pts[k][0], p[1] - pts[k][1]]);
      d.setFillColor(colorOf(it.name));
      d.setDrawColor(colorOf(it.name));
      d.setLineWidth(0.05);
      d.lines(segs, pts[0][0], pts[0][1], [1, 1], "FD", true);
      a0 = a1;
    }
  }
  pen.text(String(total), cx, cy - 4.2, { size: 15, bold: true, color: THEME.ink, align: "center" });
  pen.text("articles", cx, cy + 3.4, { size: FS, color: THEME.muted, align: "center" });
  // legend: swatch, name, count, percentage
  const lx = cx + R + 10;
  let ly = cy - (items.length * 9) / 2 + 1;
  for (const it of items) {
    pen.rect(lx, ly + 1, 3.4, 3.4, colorOf(it.name), 0.8);
    pen.text(it.name, lx + 6, ly, { size: 8.5, bold: true, color: THEME.ink });
    const pct = total > 0 ? Math.round((it.value / total) * 100) : 0;
    pen.text(`${it.value} articles · ${pct}%`, lx + 6, ly + 4.2, { size: 7.5, color: THEME.muted });
    ly += 9;
  }
}

// ---------------------------------------------------------------- horizontal bars (every label visible, counts at the bar ends)
export function drawHBars(pen: Pen, x: number, y: number, w: number, h: number, items: { name: string; value: number }[]) {
  const n = items.length;
  if (!n) return;
  const labelW = Math.min(w * 0.4, 52);
  const countW = 11;
  const barX = x + labelW + 2;
  const barMax = w - labelW - 2 - countW;
  const max = Math.max(...items.map(i => i.value), 1);
  const pitch = Math.min(9, h / n);
  const bh = Math.min(5, pitch * 0.62);
  items.forEach((it, k) => {
    const ry = y + k * pitch;
    const lines = pen.lines(it.name, labelW, 7.5, false, 2);
    const th = lines.length * pen.lh(7.5, 1.15);
    pen.text(lines.join("\n"), x, ry + (pitch - th) / 2, { size: 7.5, color: THEME.ink, w: labelW, maxLines: 2, lineHeight: 1.15 });
    const bw = Math.max(0.8, (it.value / max) * barMax);
    pen.rect(barX, ry + (pitch - bh) / 2, bw, bh, THEME.chart.series[k % 1], 0.8);
    pen.text(String(it.value), barX + bw + 1.6, ry + (pitch - pen.lh(7.5)) / 2, { size: 7.5, bold: true, color: THEME.ink });
  });
}
export const hbarsHeight = (n: number, avail: number) => Math.min(9, avail / Math.max(1, n)) * n;

// ---------------------------------------------------------------- reputation score line chart
export interface LinePoint { label: string; score: number; raw?: string }
export function drawLine(pen: Pen, x: number, y: number, w: number, h: number, pts: LinePoint[], marker?: { iso: string; label: string }) {
  const d = pen.doc;
  const ml = 9, mb = 9, mt = 5;
  const px = x + ml, pw = w - ml - 3, ph = h - mb - mt, py = y + mt;
  const lo = Math.min(...pts.map(p => p.score)), hi = Math.max(...pts.map(p => p.score));
  const ticks = niceTicks(lo - 2, hi + 2, 4);
  const ymin = ticks[0], ymax = ticks[ticks.length - 1];
  const Y = (v: number) => py + ph - ((v - ymin) / (ymax - ymin)) * ph;
  const X = (i: number) => px + (pts.length === 1 ? pw / 2 : (i / (pts.length - 1)) * pw);
  for (const t of ticks) {
    pen.line(px, Y(t), px + pw, Y(t), THEME.chart.grid, 0.2);
    pen.text(String(t), px - 1.6, Y(t) - 1.2, { size: FS, color: AX, align: "right" });
  }
  // method-change marker (vertical dashed line between the last old and first new reading)
  if (marker) {
    const cut = Date.parse(marker.iso);
    const k = pts.findIndex(p => p.raw && Date.parse(p.raw) >= cut);
    if (k > 0) {
      const mx = (X(k - 1) + X(k)) / 2;
      d.setDrawColor(THEME.neutral.dim); d.setLineWidth(0.25); d.setLineDashPattern([1.2, 1], 0); d.line(mx, py, mx, py + ph); d.setLineDashPattern([], 0);
      const left = mx > px + pw * 0.6;
      pen.text(marker.label, left ? mx - 1 : mx + 1, py + 0.4, { size: 5.8, color: THEME.neutral.label, align: left ? "right" : "left" });
    }
  }
  // line
  if (pts.length > 1) {
    d.setDrawColor(THEME.chart.line); d.setLineWidth(0.6);
    pts.slice(1).forEach((p, i) => d.line(X(i), Y(pts[i].score), X(i + 1), Y(p.score)));
  }
  const dot = pts.length <= 40 ? 1 : 0.6;
  pts.forEach((p, i) => { d.setFillColor(THEME.neutral.white); d.setDrawColor(THEME.chart.line); d.setLineWidth(0.5); d.circle(X(i), Y(p.score), dot, "FD"); });
  // value labels: every point when there are few, otherwise first, last, highest and lowest
  const idxMax = pts.findIndex(p => p.score === hi), idxMin = pts.findIndex(p => p.score === lo);
  const labelled = pts.length <= 8 ? pts.map((_, i) => i) : [...new Set([0, pts.length - 1, idxMax, idxMin])];
  for (const i of labelled) {
    const last = i === pts.length - 1 && pts.length > 1;
    pen.text(pts[i].score.toFixed(2), last ? X(i) + 1.5 : X(i), Y(pts[i].score) - 4.6, { size: 6.8, bold: true, color: THEME.ink, align: last ? "right" : "center" });
  }
  // x labels: as many as fit without touching, always including the first and last
  const maxLabels = Math.max(2, Math.floor(pw / 34));
  const step = Math.max(1, Math.ceil((pts.length - 1) / (maxLabels - 1)));
  const xs: number[] = [];
  for (let i = 0; i < pts.length; i += step) xs.push(i);
  if (pts.length > 1 && xs[xs.length - 1] !== pts.length - 1) { if (pts.length - 1 - xs[xs.length - 1] < step * 0.6) xs.pop(); xs.push(pts.length - 1); }
  for (const i of xs) pen.text(pts[i].label, X(i), py + ph + 1.8, { size: FS, color: AX, align: i === 0 && pts.length > 1 ? "left" : i === pts.length - 1 && pts.length > 1 ? "right" : "center", w: 30, maxLines: 2 });
}

// ---------------------------------------------------------------- alert timeline
export function drawTimeline(pen: Pen, x: number, y: number, w: number, h: number, pts: { date: string; count: number }[], avg: number | null) {
  const d = pen.doc;
  const ml = 8, mb = 8, mt = 5;
  const px = x + ml, pw = w - ml - 3, ph = h - mb - mt, py = y + mt;
  const max = Math.max(...pts.map(p => p.count), 1);
  const ticks = niceTicks(0, max, 3).filter(t => Number.isInteger(t));
  const ymax = ticks[ticks.length - 1] || max;
  const Y = (v: number) => py + ph - (v / ymax) * ph;
  const X = (i: number) => px + (pts.length === 1 ? pw / 2 : (i / (pts.length - 1)) * pw);
  for (const t of ticks) { pen.line(px, Y(t), px + pw, Y(t), THEME.chart.grid, 0.2); pen.text(String(t), px - 1.6, Y(t) - 1.2, { size: FS, color: AX, align: "right" }); }
  // bars (one per day) so a single day still reads as a chart
  const bw = Math.min(8, (pw / Math.max(pts.length, 1)) * 0.6);
  pts.forEach((p, i) => { if (p.count > 0) pen.rect(X(i) - bw / 2, Y(p.count), bw, Y(0) - Y(p.count), SEVERITY_RED, 0.6); });
  if (avg !== null) {
    d.setDrawColor(THEME.neutral.dim); d.setLineWidth(0.25); d.setLineDashPattern([1.2, 1], 0); d.line(px, Y(avg), px + pw, Y(avg)); d.setLineDashPattern([], 0);
    pen.text(`Avg (${avg})`, px + pw, Y(avg) - 3.6, { size: 6.3, color: THEME.neutral.label, align: "right" });
  }
  const pk = pts.reduce((b, p, i) => (p.count > pts[b].count ? i : b), 0);
  pen.text(`Peak: ${pts[pk].count}`, X(pk), Y(pts[pk].count) - 3.8, { size: 6.8, bold: true, color: THEME.ink, align: "center" });
  const maxLabels = Math.max(2, Math.floor(pw / 16));
  const step = Math.max(1, Math.ceil(pts.length / maxLabels));
  pts.forEach((p, i) => { if (i % step === 0 || i === pts.length - 1) pen.text(p.date, X(i), py + ph + 1.8, { size: FS, color: AX, align: "center", w: 20, maxLines: 1 }); });
}
const SEVERITY_RED = THEME.neutral.negative;
