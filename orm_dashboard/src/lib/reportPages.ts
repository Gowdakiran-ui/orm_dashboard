// The pages of the PDF report, composed from cards. Each function reads the report model only (never the dashboard state)
// and places its blocks through the Flow engine in reportDraw.ts.
import type { Block, Cell, NoteId, ReportAlert, ReportModel } from "@/utils/reportModel";
import type { RowCell } from "@/lib/reportDraw";
import { buildExecutiveSummary } from "@/utils/executiveSummary";
import { needsShaping } from "@/utils/reportText";
import type { TextImage } from "@/lib/reportTextImage";
import { Flow, Pen } from "@/lib/reportDraw";
import { drawDonut, drawHBars, drawLine, drawTimeline, hbarsHeight } from "@/lib/reportCharts";
import { CONTENT, PAGE, SENTIMENT_COLORS, SEVERITY, THEME } from "@/lib/reportTheme";

const T = THEME.type;
const PAD = THEME.card.pad;
const KPI_H = 31;

export interface PageCtx {
  pen: Pen;
  flow: Flow;
  model: ReportModel;
  autoTable: (doc: PageCtx["pen"]["doc"], opts: Record<string, unknown>) => void;
  textImage: (text: string, o: { maxWidthMm: number; fontSizePt: number; bold?: boolean; color?: string }) => TextImage;
  // Note numbers for tile markers, e.g. mark("positiveShare", "na") -> "[5,3]" (only notes present on the Notes page).
  mark: (...ids: NoteId[]) => string | undefined;
}

const isNA = (v: string) => v === "N/A" || v.startsWith("Unavailable");
// Marker text for a tile: a pointer to the "N/A and Unavailable" note when the value is one, plus any given notes.
const mk = (ctx: PageCtx, value: string, ...ids: NoteId[]) => ctx.mark(...(isNA(value) ? (["na"] as NoteId[]) : []), ...ids);

const sev = (s: string): { solid: string; tint: string; pale: string } => (SEVERITY as unknown as Record<string, { solid: string; tint: string; pale: string }>)[s.toUpperCase()] ?? SEVERITY.LOW;
const cellOf = (c: Cell) => (typeof c === "string" ? { text: c } : c);
const findBlock = <B extends Block["type"]>(model: ReportModel, section: string, type: B, key?: string) =>
  model.sections.find(s => s.id === section)?.blocks.find((b): b is Extract<Block, { type: B }> => b.type === type && (key === undefined || (b as { key?: string }).key === key));

// ---------------------------------------------------------------- shared card pieces
interface Kpi { label: string; value: string; sub?: string; color?: string; marker?: string }

function kpiCard(pen: Pen, x: number, y: number, w: number, h: number, k: Kpi) {
  pen.card(x, y, w, h);
  const iw = w - 2 * PAD;
  const lo = { size: T.kpiLabel, bold: true, color: THEME.muted, w: k.marker ? iw - 9 : iw, maxLines: 2, lineHeight: 1.15 };
  const labelH = pen.text(k.label, x + PAD, y + 3.2, lo);
  if (k.marker) pen.text(k.marker, x + w - PAD, y + 3.2, { size: T.tiny, bold: true, color: THEME.accent, align: "right" });
  let size = T.kpi;
  while (size > 11 && pen.width(k.value, size, true) > iw) size -= 1;
  pen.text(k.value, x + PAD, y + 3.2 + labelH + 1.2, { size, bold: true, color: k.color ?? THEME.ink, w: iw, maxLines: 1 });
  if (k.sub) pen.text(k.sub, x + PAD, y + 3.2 + labelH + 1.2 + pen.lh(size) + 0.8, { size: T.small, color: THEME.muted, w: iw, maxLines: 2 });
}

function cardTitle(pen: Pen, x: number, y: number, w: number, title: string, right?: string): number {
  pen.text(title, x + PAD, y + PAD - 0.6, { size: T.h2, bold: true, color: THEME.blue.deep, w: w - 2 * PAD });
  if (right) pen.text(right, x + w - PAD, y + PAD - 0.2, { size: T.small, color: THEME.muted, align: "right" });
  const ty = y + PAD + pen.lh(T.h2);
  pen.line(x + PAD, ty + 0.6, x + w - PAD, ty + 0.6, THEME.rule, 0.2);
  return ty + 2.6; // content top
}
const TITLE_H = PAD + 5.4 + 2.6;

function sentimentBar(pen: Pen, x: number, y: number, w: number, c: { positive: number; neutral: number; negative: number }, h = 3.6) {
  const total = c.positive + c.neutral + c.negative;
  if (total <= 0) { pen.rect(x, y, w, h, THEME.rule, h / 2); return; }
  const parts: [number, string][] = [[c.positive, SENTIMENT_COLORS.positive], [c.neutral, SENTIMENT_COLORS.neutral], [c.negative, SENTIMENT_COLORS.negative]];
  let cx = x;
  pen.rect(x, y, w, h, THEME.rule, h / 2);
  parts.forEach(([n, col], k) => {
    if (n <= 0) return;
    const pw = (n / total) * w;
    // square off inner edges, round only the outer ends
    pen.rect(cx, y, pw, h, col, 0);
    cx += pw;
    void k;
  });
}

function sectionTitle(ctx: PageCtx, title: string, sub?: string) {
  const { pen, flow } = ctx;
  const h = pen.measure(title, { size: T.h1, bold: true, w: CONTENT.w }) + (sub ? pen.measure(sub, { size: T.body, w: CONTENT.w }) : 0) + 1.5;
  flow.place(h, y => { pen.heading(title, CONTENT.x, y, sub); });
}

// ---------------------------------------------------------------- cover
export function drawCover(ctx: PageCtx) {
  const { pen, model } = ctx;
  const d = pen.doc;
  const C = THEME.cover;
  const W = PAGE.width, H = PAGE.height;
  // Full-bleed blue (painted by the page painter); a lighter panel on the right carries the score badge.
  const panelX = W * 0.66;
  pen.rect(panelX, 0, W - panelX, H, C.band);
  pen.rect(panelX, 0, 1.6, H, C.accent);

  const L = 22;
  // wordmark
  pen.rect(L, 20, 3.2, 10, C.accent, 0.6);
  pen.text("XOOP", L + 6, 19.6, { size: 22, bold: true, color: C.ink, charSpace: 1.6 });

  pen.text("Reputation Report", L, 64, { size: T.coverTitle, color: C.muted, charSpace: 0.4 });
  // client name: largest size that fits in at most two lines
  const nameW = panelX - L - 14;
  let size = T.cover;
  while (size > 18 && pen.lines(model.meta.clientName, nameW, size, true).length > 2) size -= 3;
  const nh = pen.text(model.meta.clientName, L, 74, { size, bold: true, color: C.ink, w: nameW, maxLines: 3 });
  pen.rect(L, 74 + nh + 4, 28, 1.2, C.accent, 0.6);

  let y = 74 + nh + 14;
  const meta: [string, string][] = [["Generated", model.meta.generatedAt]];
  if (model.meta.userEmail) meta.push(["Prepared for", model.meta.userEmail]);
  meta.push(["Data window", model.meta.dataWindowLine]);
  for (const [k, v] of meta) {
    pen.text(k.toUpperCase(), L, y, { size: T.tiny, bold: true, color: C.muted, charSpace: 0.6 });
    let vs = 10;
    while (vs > 8 && pen.width(v, vs) > panelX - L - 10) vs -= 0.5;
    const vh = pen.text(v, L, y + 4, { size: vs, color: C.ink, w: panelX - L - 10, maxLines: 2 });
    y += 4 + vh + 5;
  }

  // score badge
  const f = model.facts.score;
  const cx = panelX + (W - panelX) / 2;
  const cy = H / 2 - 4;
  d.setFillColor(THEME.neutral.white);
  d.circle(cx, cy, 34, "F");
  d.setDrawColor(C.accent);
  d.setLineWidth(1.6);
  d.circle(cx, cy, 36.5, "S");
  pen.text("REPUTATION SCORE", cx, cy - 22, { size: T.kpiLabel, bold: true, color: THEME.muted, align: "center", charSpace: 0.5 });
  const known = f.state === "ok";
  const shown = f.state === "unavailable" ? "Unavailable" : f.display;
  let ss = 36;
  while (ss > 14 && pen.width(shown, ss, true) > 56) ss -= 2;
  pen.text(shown, cx, cy - 10, { size: ss, bold: true, color: THEME.blue.deep, align: "center" });
  if (known) {
    pen.pill(`GRADE ${f.grade}`, cx - pen.width(`GRADE ${f.grade}`, T.tiny, true) / 2 - 2, cy + 14, { fill: THEME.accent, size: 8.5, h: 6.4 });
  } else {
    pen.text(f.state === "na" ? (f.statusText || "Not enough data yet") : "Data could not be loaded", cx, cy + 12, { size: T.small, color: THEME.muted, align: "center", w: 52, maxLines: 2 });
  }
  if (f.asOf) pen.text(`as of ${f.asOf}`, cx, cy + 40, { size: T.small, color: C.muted, align: "center", w: W - panelX - 12, maxLines: 2 });
}

// ---------------------------------------------------------------- executive summary
export function drawSummary(ctx: PageCtx) {
  const { pen, flow, model } = ctx;
  const s = buildExecutiveSummary(model.facts, model.meta.clientName);
  sectionTitle(ctx, "Executive Summary", `${s.clientName} · ${s.headline.known ? `Reputation Score ${s.headline.score} (Grade ${s.headline.grade})${s.headline.asOf ? `, as of ${s.headline.asOf}` : ""}` : s.headline.score === "Unavailable" ? "Reputation data is unavailable" : "Reputation score not available yet"}`);

  const n = s.kpis.length;
  const kw = (CONTENT.w - PAGE.gutter * (n - 1)) / n;
  flow.place(KPI_H, y => s.kpis.forEach((k, i) => kpiCard(pen, CONTENT.x + i * (kw + PAGE.gutter), y, kw, KPI_H, { ...k, color: kpiColor(k), marker: mk(ctx, k.value, ...(k.label === "Flagged Articles" && model.facts.risk.unscored > 0 ? ["unscored" as NoteId] : [])) })));

  // What happened | Top risks
  flow.row([
    {
      span: 7,
      measure: w => TITLE_H + s.sentences.reduce((a, t) => a + pen.measure(t, { size: T.body + 0.5, w: w - 2 * PAD - 4 }) + 1.8, 0) + PAD - 1,
      draw: (x, y, w) => {
        let cy = cardTitle(pen, x, y, w, "What happened");
        for (const t of s.sentences) {
          pen.rect(x + PAD, cy + 1.3, 1.4, 1.4, THEME.accent, 0.7);
          cy += pen.text(t, x + PAD + 4, cy, { size: T.body + 0.5, w: w - 2 * PAD - 4 }) + 1.8;
        }
      },
    },
    {
      span: 5,
      measure: w => TITLE_H + (s.topRisks.length ? s.topRisks.reduce((a, r) => a + riskItemH(pen, r, w - 2 * PAD), 0) : 6) + (s.topRisksNote ? 5 : 0) + PAD - 1,
      draw: (x, y, w) => {
        let cy = cardTitle(pen, x, y, w, "Top risks");
        for (const r of s.topRisks) cy += drawRiskItem(pen, r, x + PAD, cy, w - 2 * PAD);
        if (s.topRisksNote) pen.text(s.topRisksNote, x + PAD, cy + (s.topRisks.length ? 0 : 0), { size: T.small, color: THEME.muted, w: w - 2 * PAD });
      },
    },
  ]);

  // Open alerts | Coverage snapshot
  flow.row([
    {
      span: 7,
      measure: w => TITLE_H + (s.openAlerts.length ? s.openAlerts.reduce((a, al) => a + alertItemH(pen, al, w - 2 * PAD), 0) : 0) + (s.openAlertsNote ? 6 : 0) + PAD - 1,
      draw: (x, y, w) => {
        let cy = cardTitle(pen, x, y, w, "Open alerts");
        for (const al of s.openAlerts) cy += drawAlertItem(pen, al, x + PAD, cy, w - 2 * PAD);
        if (s.openAlertsNote) pen.text(s.openAlertsNote, x + PAD, cy, { size: T.body, color: THEME.muted, w: w - 2 * PAD });
      },
    },
    {
      span: 5,
      measure: w => TITLE_H + 14 + (s.topTopics.length ? s.topTopics.length * 5.2 + 6 : 6) + PAD - 1 + (w > 0 ? 0 : 0),
      draw: (x, y, w) => {
        let cy = cardTitle(pen, x, y, w, "Coverage snapshot");
        const iw = w - 2 * PAD;
        if (s.tone) {
          pen.text(`Tone of mentions: ${s.toneLabel}`, x + PAD, cy, { size: T.small, bold: true, color: THEME.ink });
          sentimentBar(pen, x + PAD, cy + 4.6, iw, s.tone);
          pen.text(`${s.tone.positive} positive · ${s.tone.neutral} neutral · ${s.tone.negative} negative`, x + PAD, cy + 9.2, { size: T.small, color: THEME.muted, w: iw });
        } else pen.text(`Tone of mentions: ${s.toneLabel === "Unavailable" ? "Unavailable" : "Not enough data yet"}`, x + PAD, cy, { size: T.small, color: THEME.muted, w: iw });
        cy += 14;
        if (s.topTopics.length) {
          pen.text("Top topics (articles)", x + PAD, cy, { size: T.small, bold: true });
          cy += 5;
          for (const t of s.topTopics) {
            pen.text(t.name, x + PAD, cy, { size: T.body, w: iw - 14, maxLines: 1 });
            pen.text(String(t.count), x + w - PAD, cy, { size: T.body, bold: true, align: "right" });
            cy += 5.2;
          }
        } else pen.text(s.topicsNote ?? "Not enough data yet", x + PAD, cy, { size: T.body, color: THEME.muted, w: iw });
      },
    },
  ]);
}

function kpiColor(k: { label: string; value: string }): string | undefined {
  if (k.label === "Risk Signals" && /^[1-9]/.test(k.value)) return SEVERITY.CRITICAL.solid;
  return undefined;
}

function riskItemH(pen: Pen, r: { title: string }, w: number) { return pen.measure(r.title, { size: T.body, bold: true, w, maxLines: 2 }) + 4.6 + 2; }
function drawRiskItem(pen: Pen, r: { title: string; severity: string; source: string; date: string; score: string }, x: number, y: number, w: number): number {
  const c = sev(r.severity);
  const th = pen.text(r.title, x + 3, y, { size: T.body, bold: true, w: w - 3, maxLines: 2 });
  const pw = pen.pill(`${r.severity} · ${r.score}`, x + 3, y + th + 0.6, { fill: c.solid, size: T.tiny });
  pen.text(`${r.source} · ${r.date}`, x + 3 + pw + 2, y + th + 0.9, { size: T.tiny + 0.5, color: THEME.muted, w: w - pw - 6, maxLines: 1 });
  pen.rect(x, y, 1, th + 5, c.solid, 0.5);
  return th + 4.6 + 2;
}

function alertItemH(pen: Pen, a: { title: string }, w: number) { return pen.measure(a.title, { size: T.body, bold: true, w: w - 3, maxLines: 2 }) + 4.4 + 2; }
function drawAlertItem(pen: Pen, a: { title: string; severity: string; raised: string }, x: number, y: number, w: number): number {
  const c = sev(a.severity);
  const th = pen.text(a.title, x + 3, y, { size: T.body, bold: true, w: w - 3, maxLines: 2 });
  const pw = pen.pill(a.severity, x + 3, y + th + 0.6, { fill: c.solid, size: T.tiny });
  pen.text(`raised ${a.raised}`, x + 3 + pw + 2, y + th + 0.9, { size: T.tiny + 0.5, color: THEME.muted, maxLines: 1 });
  pen.rect(x, y, 1, th + 5, c.solid, 0.5);
  return th + 4.4 + 2;
}

// ---------------------------------------------------------------- risk center
const ALERT_COLS = [0.4, 0.2, 0.4];

function alertH(pen: Pen, a: ReportAlert, w: number): number {
  const titleH = pen.measure(a.title, { size: T.body + 0.5, bold: true, w: w - 24, maxLines: 2 });
  const h = Math.max(titleH, 4.4) + pen.lh(T.small) + 1.5;
  if (a.what === null) return h + pen.lh(T.small) + 3;
  const cw = ALERT_COLS.map(r => (w - 3 * 2) * r);
  const body = [a.what, a.when ?? "Unknown", a.nextStep ?? ""].map((t, k) => pen.measure(t, { size: T.small + 0.3, w: cw[k], maxLines: 6 }));
  return h + pen.lh(T.tiny) + Math.max(...body) + 3;
}

function drawAlert(pen: Pen, a: ReportAlert, x: number, y: number, w: number) {
  const c = sev(a.severity);
  const top = y;
  const pw = pen.pill(a.severity, x + 3, y, { fill: c.solid });
  const titleH = pen.text(a.title, x + 3 + pw + 2, y, { size: T.body + 0.5, bold: true, w: w - pw - 5, maxLines: 2 });
  y += Math.max(titleH, 4.4) + 0.4;
  y += pen.text(`${a.alertType} · raised ${a.raised}`, x + 3, y, { size: T.small, color: THEME.muted, w: w - 3, maxLines: 1 }) + 1.5;
  if (a.what === null) {
    y += pen.text("Suggested next step not yet generated for this alert.", x + 3, y, { size: T.small, color: THEME.muted }) + 3;
  } else {
    const cw = ALERT_COLS.map(r => (w - 3 - 3 * 2) * r);
    const labels = ["Why this was flagged", "When", "Suggested next step"];
    const texts = [a.what, a.when ?? "Unknown", a.nextStep ?? ""];
    let cx = x + 3, bh = 0;
    texts.forEach((t, k) => {
      pen.text(labels[k].toUpperCase(), cx, y, { size: T.tiny - 0.5, bold: true, color: THEME.muted, charSpace: 0.3 });
      bh = Math.max(bh, pen.text(t, cx, y + pen.lh(T.tiny), { size: T.small + 0.3, w: cw[k], maxLines: 6 }));
      cx += cw[k] + 3;
    });
    y += pen.lh(T.tiny) + bh + 3;
  }
  pen.rect(x, top, 1, y - top - 1.5, c.solid, 0.5);
  return y - top;
}

// How many of the alerts fit in maxH (at least one).
function alertsThatFit(pen: Pen, alerts: ReportAlert[], w: number, maxH: number): number {
  let used = 0, n = 0;
  for (const a of alerts) {
    const h = alertH(pen, a, w) + 1.5;
    if (n > 0 && used + h > maxH) break;
    used += h; n++;
  }
  return n;
}

export function drawRiskCenter(ctx: PageCtx) {
  const { pen, flow, model } = ctx;
  const f = model.facts;
  const tilesBlock = findBlock(model, "risk-center", "stats", "rc-tiles");
  sectionTitle(ctx, "Risk Center", f.risk.asOf ? `All-time counts · scores as of ${f.risk.asOf}` : "All-time counts");

  // five tiles
  if (tilesBlock) {
    const items = tilesBlock.items;
    const n = items.length;
    const tw = (CONTENT.w - PAGE.gutter * (n - 1)) / n;
    const colors: Record<string, string> = { Critical: SEVERITY.CRITICAL.solid, High: SEVERITY.HIGH.solid, Medium: SEVERITY.MEDIUM.solid };
    flow.place(KPI_H, y => items.forEach((it, i) => {
      const num = /^\d/.test(it.value) && it.value !== "0";
      kpiCard(pen, CONTENT.x + i * (tw + PAGE.gutter), y, tw, KPI_H, {
        label: it.label, value: it.value, color: num ? colors[it.label] : undefined,
        marker: mk(ctx, it.value, ...(it.label === "Flagged Articles" && f.risk.unscored > 0 ? ["unscored" as NoteId] : it.label === "Highest Score" ? ["riskLevels" as NoteId] : [])),
        sub: it.label === "Flagged Articles" && f.risk.unscored > 0 ? `${f.risk.unscored} not risk-checked yet` : it.label === "Highest Score" ? "of 100" : undefined,
      });
    }));
  } else {
    flow.place(14, y => { pen.card(CONTENT.x, y, CONTENT.w, 14); pen.text("Unavailable (data could not be loaded)", CONTENT.x + PAD, y + 4.5, { size: T.body, color: THEME.muted }); });
  }

  // matrix | active alerts
  const matrix = findBlock(model, "risk-center", "table", "rc-matrix");
  const alerts = f.alerts.items;
  const MATRIX_W = 108;
  const ALERT_CAP = 74;
  const alertW = CONTENT.w - MATRIX_W - PAGE.gutter - 2 * PAD;
  const first = alerts.length ? alertsThatFit(pen, alerts, alertW, ALERT_CAP) : 0;
  const matrixH = TITLE_H + 7 + 3 * 12 + PAD + 2;
  const alertsBodyH = (list: ReportAlert[]) => list.reduce((a, al) => a + alertH(pen, al, alertW) + 1.5, 0);
  const riskRow: RowCell[] = [
    {
      span: 4,
      measure: () => matrixH,
      draw: (x, y, w) => drawMatrix(pen, matrix, x, y, w, !!matrix, ctx.mark("confidence", "riskLevels")),
    },
    {
      span: 6,
      measure: () => TITLE_H + (alerts.length ? alertsBodyH(alerts.slice(0, first)) : 7) + PAD,
      draw: (x, y, w) => {
        const cy = cardTitle(pen, x, y, w, f.alerts.state === "ok" ? `Active alerts${alerts.length ? ` (${alerts.length})` : ""}` : "Active alerts");
        if (alerts.length) pen.pill("AI-generated analysis", x + w - PAD - 30, y + PAD - 1.4, { fill: THEME.blue.soft, color: THEME.blue.deep });
        drawAlertsBody(pen, alerts.slice(0, first), f.alerts.state, x + PAD, cy, w - 2 * PAD);
      },
    },
  ];
  flow.row(riskRow);

  // alerts that did not fit beside the matrix continue in full-width cards
  let done = first;
  while (done < alerts.length) {
    const fw = CONTENT.w - 2 * PAD;
    flow.ensure(TITLE_H + 40);
    const avail = flow.left - TITLE_H - PAD;
    const k = alertsThatFit(pen, alerts.slice(done), fw, avail);
    const chunk = alerts.slice(done, done + k);
    flow.row([{
      span: 1,
      measure: () => TITLE_H + chunk.reduce((a, al) => a + alertH(pen, al, fw) + 1.5, 0) + PAD,
      draw: (x, y, w) => { const cy = cardTitle(pen, x, y, w, "Active alerts (continued)"); drawAlertsBody(pen, chunk, "ok", x + PAD, cy, w - 2 * PAD); },
    }]);
    done += k;
  }

  // flagged articles table (continues on the next pages with its header row repeated)
  drawFlaggedTable(ctx);
}

function drawAlertsBody(pen: Pen, list: ReportAlert[], state: "ok" | "unavailable", x: number, y: number, w: number) {
  if (state === "unavailable") { pen.text("Unavailable (data could not be loaded)", x, y, { size: T.body, color: THEME.muted }); return; }
  if (list.length === 0) { pen.text("No unacknowledged alerts.", x, y, { size: T.body, color: THEME.muted }); return; }
  let cy = y;
  for (const a of list) cy += drawAlert(pen, a, x, cy, w) + 1.5;
}

function drawMatrix(pen: Pen, block: Extract<Block, { type: "table" }> | undefined, x: number, y: number, w: number, ok: boolean, markText?: string) {
  let cy = cardTitle(pen, x, y, w, "Severity × Confidence", markText);
  if (!block || !ok) { pen.text("Unavailable (data could not be loaded)", x + PAD, cy, { size: T.body, color: THEME.muted }); return; }
  const iw = w - 2 * PAD;
  const lw = 22;
  const cw = (iw - lw) / 3;
  // header
  block.columns.slice(1).forEach((c, k) => pen.text(c.replace(" CONFIDENCE", "").toLowerCase().replace(/^./, m => m.toUpperCase()) + " conf.", x + PAD + lw + k * cw + cw / 2, cy, { size: T.tiny, bold: true, color: THEME.muted, align: "center" }));
  cy += 6;
  block.rows.forEach(row => {
    row.forEach((raw, k) => {
      const c = cellOf(raw);
      const cx = k === 0 ? x + PAD : x + PAD + lw + (k - 1) * cw;
      const cwid = k === 0 ? lw - 1.5 : cw - 1.5;
      pen.rect(cx, cy, cwid, 10.5, c.fill ?? THEME.neutral.cell, 1.5);
      pen.text(c.text, cx + cwid / 2, cy + (10.5 - pen.lh(T.small)) / 2, { size: k === 0 ? T.small : T.small, bold: k === 0 || !!c.bold, color: c.color ?? THEME.ink, align: "center", w: cwid - 1, maxLines: 1 });
    });
    cy += 12;
  });
}

function drawFlaggedTable(ctx: PageCtx) {
  const { pen, flow, model } = ctx;
  const d = pen.doc;
  const table = findBlock(model, "risk-center", "table", "rc-flagged");
  const notes = model.sections.find(s => s.id === "risk-center")!.blocks.filter(b => b.type === "text" && b.style === "note").map(b => (b as { text: string }).text);
  const flaggedTitle = "Flagged Articles";
  // keep the heading with at least a header row and two rows
  const headH = pen.measure(flaggedTitle, { size: T.h2 + 1, bold: true });
  flow.startSection(headH + 8 + 2 * 9);
  flow.place(headH + 1, y => {
    pen.text(flaggedTitle, CONTENT.x, y, { size: T.h2 + 1, bold: true, color: THEME.page.headerInk });
    const m = ctx.mark("window", "riskLevels");
    if (m) pen.text(m, CONTENT.x + pen.width(flaggedTitle, T.h2 + 1, true) + 2, y + 1.2, { size: T.tiny, bold: true, color: THEME.page.headerMuted });
  });
  const noteLines = notes.filter(n => /Showing the|Listing the/.test(n));
  for (const n of noteLines) flow.place(pen.measure(n, { size: T.small, w: CONTENT.w }), y => { pen.text(n, CONTENT.x, y, { size: T.small, color: THEME.page.headerMuted, w: CONTENT.w }); });
  if (!table) {
    const none = model.sections.find(sec => sec.id === "risk-center")!.blocks.some(blk => blk.type === "text" && blk.text === "No flagged articles.");
    flow.place(8, y => pen.text(none ? "No flagged articles." : UNAVAIL, CONTENT.x, y, { size: T.body, color: THEME.page.headerMuted }));
    return;
  }
  const sumW = [100, 14, 20, 40, 40, 22, 37];
  const total = sumW.reduce((a, b) => a + b, 0);
  const widths = sumW.map(v => (v / total) * CONTENT.w);
  const fs = T.table;
  d.setFontSize(fs);
  const body = table.rows.map(r => r.map((raw, ci) => {
    const c = cellOf(raw);
    const styles: Record<string, unknown> = {};
    if (c.fill) styles.fillColor = c.fill;
    if (c.color) styles.textColor = c.color;
    if (c.align) styles.halign = c.align;
    if (c.bold) styles.fontStyle = "bold";
    const inner = widths[ci] - 3.2;
    if (needsShaping(c.text)) {
      const img = ctx.textImage(c.text, { maxWidthMm: inner, fontSizePt: fs, bold: c.bold, color: c.color ?? THEME.ink });
      return { content: "", styles: { ...styles, minCellHeight: img.heightMm + 3.2 }, _img: img };
    }
    // at most two lines per cell, with an ellipsis; row heights stay even
    const text = ci === 0 || ci === 3 || ci === 6 ? pen.lines(c.text, inner, fs, !!c.bold, 2).join("\n") : c.text;
    return { content: text, styles };
  }));
  const startPage = d.getNumberOfPages();
  ctx.autoTable(d, {
    startY: flow.y,
    head: [table.columns],
    body,
    theme: "plain",
    margin: { top: CONTENT.y, bottom: PAGE.height - CONTENT.bottom, left: CONTENT.x, right: PAGE.width - CONTENT.x - CONTENT.w },
    tableWidth: CONTENT.w,
    styles: { font: "NotoSans", fontSize: fs, cellPadding: { top: 1.8, bottom: 1.8, left: 1.6, right: 1.6 }, textColor: THEME.ink, lineColor: THEME.table.line, lineWidth: 0, overflow: "linebreak", valign: "middle", fillColor: THEME.neutral.white },
    headStyles: { fillColor: THEME.table.headFill, textColor: THEME.table.headInk, fontStyle: "bold", halign: "left" },
    alternateRowStyles: { fillColor: THEME.table.zebra },
    columnStyles: Object.fromEntries(widths.map((w, i) => [i, { cellWidth: w }])),
    rowPageBreak: "avoid",
    showHead: "everyPage",
    willDrawPage: () => { flow.markPainted(d.getNumberOfPages()); },
    didDrawCell: (data: { cell: { x: number; y: number; height: number; raw?: { _img?: TextImage } }; section: string }) => {
      flow.noteExtent(d.getCurrentPageInfo().pageNumber, data.cell.y + data.cell.height);
      const img: TextImage | undefined = data.cell.raw?._img;
      if (img && data.section === "body") d.addImage(img.dataUrl, "PNG", data.cell.x + 1.6, data.cell.y + 1.8, img.widthMm, img.heightMm);
    },
  });
  void startPage;
  flow.page = d.getNumberOfPages();
  d.setPage(flow.page);
  const endY = (d as unknown as { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY ?? flow.y;
  flow.y = endY + PAGE.rowGap;
  flow.noteExtent(flow.page, endY);
}


// ---------------------------------------------------------------- shared card builders
const UNAVAIL = "Unavailable (data could not be loaded)";

function statsRow(ctx: PageCtx, items: { label: string; value: string; sub?: string }[], markers: Record<string, NoteId[]> = {}) {
  const { pen, flow } = ctx;
  const n = items.length;
  const kw = (CONTENT.w - PAGE.gutter * (n - 1)) / n;
  flow.place(KPI_H, y => items.forEach((it, i) => kpiCard(pen, CONTENT.x + i * (kw + PAGE.gutter), y, kw, KPI_H, { ...it, marker: mk(ctx, it.value, ...(markers[it.label] ?? [])) })));
}

function messageCard(ctx: PageCtx, title: string, lines: string[], span: number, marker?: string): RowCell {
  const { pen } = ctx;
  return {
    span,
    measure: w => TITLE_H + lines.reduce((a, t) => a + pen.measure(t, { size: T.body + 0.5, w: w - 2 * PAD }) + 1.6, 0) + PAD - 1,
    draw: (x, y, w) => {
      let cy = cardTitle(pen, x, y, w, title, marker);
      for (const t of lines) cy += pen.text(t, x + PAD, cy, { size: T.body + 0.5, w: w - 2 * PAD }) + 1.6;
    },
  };
}

// ---------------------------------------------------------------- brand equity
export function drawBrandEquity(ctx: PageCtx) {
  const { pen, flow, model } = ctx;
  const f = model.facts;
  const glance = findBlock(model, "brand-equity", "stats", "be-glance");
  sectionTitle(ctx, "Brand Equity", f.texts.verdict || undefined);
  if (!glance) {
    flow.row([messageCard(ctx, "Brand Equity", [UNAVAIL], 12)]);
    return;
  }
  const item = (label: string) => glance.items.find(i => i.label.startsWith(label)) ?? { label, value: "N/A", sub: "" };
  const score = item("Reputation Score"), signals = item("Risk Signals"), total = item("Total Risks"), pos = item("Positive mentions"), tone = item("Overall Tone");
  const H = 48;
  flow.row([
    {
      span: 4, measure: () => H,
      draw: (x, y, w) => {
        pen.text("REPUTATION SCORE", x + PAD, y + 3.4, { size: T.kpiLabel, bold: true, color: THEME.muted, charSpace: 0.3 });
        const m = mk(ctx, score.value); if (m) pen.text(m, x + w - PAD, y + 3.4, { size: T.tiny, bold: true, color: THEME.accent, align: "right" });
        let size = 30; while (size > 14 && pen.width(score.value, size, true) > w - 2 * PAD) size -= 2;
        pen.text(score.value, x + PAD, y + 9, { size, bold: true, color: THEME.blue.deep, w: w - 2 * PAD, maxLines: 1 });
        if (f.score.state === "ok") {
          pen.pill(`GRADE ${f.score.grade}`, x + PAD, y + 9 + pen.lh(size) + 1.5, { fill: THEME.accent, size: 8, h: 6 });
          if (f.score.asOf) pen.text(`as of ${f.score.asOf}`, x + PAD, y + H - PAD - 3, { size: T.small, color: THEME.muted, w: w - 2 * PAD, maxLines: 1 });
        } else pen.text(f.score.statusText || (f.score.state === "unavailable" ? "Data could not be loaded" : "Not enough data yet"), x + PAD, y + 9 + pen.lh(size) + 1.5, { size: T.small, color: THEME.muted, w: w - 2 * PAD, maxLines: 2 });
      },
    },
    {
      span: 4, measure: () => H,
      draw: (x, y, w) => {
        const half = (w - 2 * PAD) / 2;
        const col = (k: number, label: string, value: string, sub: string, color?: string) => {
          const cx = x + PAD + k * half;
          pen.text(label, cx, y + 3.4, { size: T.kpiLabel, bold: true, color: THEME.muted, w: half - 2, maxLines: 2, lineHeight: 1.1 });
          pen.text(value, cx, y + 11, { size: 24, bold: true, color: color ?? THEME.ink, w: half - 2, maxLines: 1 });
          pen.text(sub, cx, y + 11 + pen.lh(24) + 0.6, { size: T.small, color: THEME.muted, w: half - 2, maxLines: 2 });
        };
        col(0, "RISK SIGNALS", signals.value, "Critical + High", /^[1-9]/.test(signals.value) ? SEVERITY.CRITICAL.solid : undefined);
        col(1, "TOTAL RISKS TRACKED", total.value, total.sub ?? "");
        const m = mk(ctx, `${signals.value}${total.value}`); if (m) pen.text(m, x + w - PAD, y + 3.4, { size: T.tiny, bold: true, color: THEME.accent, align: "right" });
      },
    },
    {
      span: 4, measure: () => H,
      draw: (x, y, w) => {
        const half = (w - 2 * PAD) / 2;
        pen.text("POSITIVE MENTIONS (BRAND-GATED)", x + PAD, y + 3.4, { size: T.kpiLabel, bold: true, color: THEME.muted, w: half - 2, maxLines: 2, lineHeight: 1.1 });
        pen.text(pos.value, x + PAD, y + 11, { size: 24, bold: true, w: half - 2, maxLines: 1 });
        pen.text("in coverage", x + PAD, y + 11 + pen.lh(24) + 0.6, { size: T.small, color: THEME.muted });
        pen.text("OVERALL TONE", x + PAD + half, y + 3.4, { size: T.kpiLabel, bold: true, color: THEME.muted });
        let ts = 18; while (ts > 10 && pen.width(tone.value, ts, true) > half - 2) ts -= 1;
        pen.text(tone.value, x + PAD + half, y + 11.5, { size: ts, bold: true, w: half - 2, maxLines: 1 });
        const c = f.tone;
        if (c.positive !== null && c.neutral !== null && c.negative !== null) {
          sentimentBar(pen, x + PAD + half, y + 11.5 + pen.lh(ts) + 1.5, half - 2, { positive: c.positive, neutral: c.neutral, negative: c.negative });
          pen.text(`${c.positive} pos · ${c.neutral} neu · ${c.negative} neg`, x + PAD + half, y + 11.5 + pen.lh(ts) + 6.4, { size: T.tiny + 0.3, color: THEME.muted, w: half - 2, maxLines: 1 });
        }
        const m = mk(ctx, pos.value, "positiveMentions"); if (m) pen.text(m, x + w - PAD, y + 3.4, { size: T.tiny, bold: true, color: THEME.accent, align: "right" });
      },
    },
  ]);

  const mean: string[] = [f.texts.riskProfile, f.texts.sentiment];
  if (f.texts.advisory) mean.push(f.texts.advisory);
  flow.row([
    messageCard(ctx, "What this means", mean, 8),
    messageCard(ctx, "Alerts", [f.texts.alertLine], 4),
  ], 44);
  flow.row([
    messageCard(ctx, "Notable people in coverage", [f.texts.people], 6),
    messageCard(ctx, "Competitive standing", [f.texts.standing], 6),
  ], 30);
}

// ---------------------------------------------------------------- executive analytics
function chartCard(ctx: PageCtx, span: number, title: string, caption: string, marker: string | undefined, bodyH: number, body: (x: number, y: number, w: number, h: number) => void): RowCell {
  const { pen } = ctx;
  return {
    span,
    measure: w => TITLE_H + pen.measure(caption, { size: T.small, w: w - 2 * PAD }) + 2 + bodyH + PAD,
    draw: (x, y, w, h) => {
      let cy = cardTitle(pen, x, y, w, title, marker);
      cy += pen.text(caption, x + PAD, cy, { size: T.small, color: THEME.muted, w: w - 2 * PAD }) + 2;
      body(x + PAD, cy, w - 2 * PAD, h - (cy - y) - PAD);
    },
  };
}

function emptyBody(pen: Pen, text: string, sub?: string) {
  return (x: number, y: number, w: number, h: number) => {
    pen.rect(x, y, w, h, THEME.neutral.panel, 2);
    const th = pen.measure(text, { size: 10, bold: true, w: w - 8 }) + (sub ? pen.measure(sub, { size: T.small, w: w - 8 }) + 1 : 0);
    let cy = y + (h - th) / 2;
    cy += pen.text(text, x + w / 2, cy, { size: 10, bold: true, color: THEME.blue.deep, align: "center", w: w - 8 }) + 1;
    if (sub) pen.text(sub, x + w / 2, cy, { size: T.small, color: THEME.muted, align: "center", w: w - 8 });
  };
}

export function drawAnalyticsSentimentTopics(ctx: PageCtx) {
  const { pen, flow, model } = ctx;
  const dta = model.data;
  const overview = findBlock(model, "executive-analytics", "stats", "ea-overview");
  sectionTitle(ctx, "Executive Analytics · Sentiment and topics");
  if (overview) statsRow(ctx, overview.items.map(i => ({ label: i.label, value: i.value, sub: i.sub })), { "Positive share (document sentiment)": ["positiveShare"], "Topics Covered": ["topicFloor"] });
  else flow.row([messageCard(ctx, "Reputation & Sentiment History", [UNAVAIL], 12)]);

  const NB = 78; // body height for charts
  const topicsH = dta.topics.items.length ? hbarsHeight(dta.topics.items.length, NB) : 30;
  const bodyH = Math.max(62, topicsH);
  flow.row([
    chartCard(ctx, 5, "Sentiment Breakdown", dta.captions.sentiment, undefined, bodyH, (x, y, w, h) => {
      if (dta.sentiment.state === "ok" && dta.sentiment.items.length) drawDonut(pen, x, y, w, h, dta.sentiment.items);
      else emptyBody(pen, dta.sentiment.state === "unavailable" ? UNAVAIL : "No sentiment distribution data.")(x, y, w, Math.min(h, 40));
    }),
    chartCard(ctx, 7, "Coverage by Topic", dta.captions.topics, ctx.mark("topicFloor"), bodyH, (x, y, w, h) => {
      if (dta.topics.state === "ok" && dta.topics.items.length) drawHBars(pen, x, y, w, h, dta.topics.items);
      else emptyBody(pen, dta.topics.state === "unavailable" ? UNAVAIL : "No topics mapped.")(x, y, w, Math.min(h, 40));
    }),
  ]);
}

export function drawAnalyticsHistoryAlerts(ctx: PageCtx) {
  const { pen, flow, model } = ctx;
  const dta = model.data;
  const risk = findBlock(model, "executive-analytics", "stats", "ea-risk");
  sectionTitle(ctx, "Executive Analytics · History and alerts");
  if (risk) statsRow(ctx, risk.items.map(i => ({ label: i.label, value: i.value, sub: i.sub })), { "Avg Risk Score (Listed Feed)": ["listedFeed"] });
  else flow.row([messageCard(ctx, "Risk & Alert Profile", [UNAVAIL], 12)]);
  const H = 66;
  const hist = dta.repHistory;
  const histMark = ctx.mark("times", ...(hist.methodChange ? (["scoringChange"] as NoteId[]) : []));
  flow.row([
    chartCard(ctx, 7, "Reputation Score History", dta.captions.repHistory, histMark, H, (x, y, w) => {
      if (hist.state === "unavailable") emptyBody(pen, UNAVAIL)(x, y, w, H);
      else if (hist.points.length >= 2) drawLine(pen, x, y, w, H, hist.points, hist.methodChange ? { iso: "2026-10-01T00:00:00Z", label: "Scoring method updated" } : undefined);
      else if (hist.points.length === 1) {
        pen.rect(x, y, w, H, THEME.neutral.panel, 2);
        pen.text("SINGLE READING", x + w / 2, y + H / 2 - 17, { size: T.kpiLabel, bold: true, color: THEME.muted, align: "center", charSpace: 0.4 });
        pen.text(hist.points[0].score.toFixed(2), x + w / 2, y + H / 2 - 11, { size: 30, bold: true, color: THEME.blue.deep, align: "center" });
        pen.text(`stored ${hist.points[0].at}`, x + w / 2, y + H / 2 + 5, { size: T.body, color: THEME.muted, align: "center" });
        pen.text("A line appears once there are two or more stored scores.", x + w / 2, y + H / 2 + 11, { size: T.small, color: THEME.muted, align: "center", w: w - 8 });
      } else emptyBody(pen, "No historical reputation data available.")(x, y, w, H);
    }),
    chartCard(ctx, 5, "Daily Alerts Trigger Volume", dta.captions.alerts, ctx.mark("times"), H, (x, y, w) => {
      const a = dta.alerts;
      if (a.state === "unavailable") emptyBody(pen, UNAVAIL)(x, y, w, H);
      else if (a.state === "empty") emptyBody(pen, "No open alerts", "Nothing unacknowledged for this client.")(x, y, w, H);
      else if (a.points.length === 0) emptyBody(pen, "N/A", "Alert counts could not be read.")(x, y, w, H);
      else {
        drawTimeline(pen, x, y, w, H - 6, a.points, a.countsOk ? Number(a.avg) : null);
        pen.text(a.countsOk ? `Avg (${a.avg}) · Peak: ${a.peak}${a.peakDate ? ` on ${a.peakDate}` : ""}` : "Avg (N/A) · Peak: N/A", x, y + H - 4.5, { size: T.small, color: THEME.muted });
      }
    }),
  ]);
}

// ---------------------------------------------------------------- heatmap
export function drawHeatmap(ctx: PageCtx) {
  const { pen, flow, model } = ctx;
  const table = findBlock(model, "executive-analytics", "table", "ea-heatmap");
  const st = model.data.heatmap.state;
  const mark = ctx.mark("unscored", "topicFloor");
  sectionTitle(ctx, "Threat Concentration Heatmap", `Severity × topic: articles per cell and share of the topic's articles${mark ? `  ${mark}` : ""}`);
  if (!table || st !== "ok") {
    const msg = st === "unavailable" ? UNAVAIL : st === "na" ? "N/A (the heatmap counts could not be read)." : "No active risk events.";
    flow.row([messageCard(ctx, "Heatmap", [msg], 12)]);
    return;
  }
  const rows = table.rows;
  const inner = CONTENT.w - 2 * PAD;
  const fixed = [44, 22, 18];
  const sevW = (inner - fixed[0] - fixed[1] - fixed[2]) / 4;
  const widths = [fixed[0], sevW, sevW, sevW, sevW, fixed[1], fixed[2]];
  const headH = 7;
  const avail = CONTENT.bottom - CONTENT.y - 16 - TITLE_H - PAD;
  const rowH = Math.max(9, Math.min(13, (avail - headH) / rows.length));
  const drawChunk = (chunk: Cell[][], first: boolean) => {
    const hh = TITLE_H + headH + chunk.length * rowH + PAD;
    flow.place(hh, y => {
      const x = CONTENT.x;
      pen.card(x, y, CONTENT.w, hh);
      let cy = cardTitle(pen, x, y, CONTENT.w, first ? "Articles by topic and risk level" : "Articles by topic and risk level (continued)");
      let cx = x + PAD;
      table.columns.forEach((c, k) => { pen.text(c, cx + widths[k] / 2, cy + 1, { size: T.tiny, bold: true, color: THEME.muted, align: "center", charSpace: 0.3 }); cx += widths[k]; });
      cy += headH;
      chunk.forEach(row => {
        cx = x + PAD;
        row.forEach((raw, k) => {
          const c = cellOf(raw);
          const lines = c.text.split("\n");
          if (k === 0) pen.text(c.text, cx + 1, cy + (rowH - 1.4 - pen.lh(T.body)) / 2, { size: T.body, bold: true, w: widths[0] - 2, maxLines: 2, lineHeight: 1.1 });
          else if (k >= 5) pen.text(c.text, cx + widths[k] / 2, cy + (rowH - 1.4 - pen.lh(T.body)) / 2, { size: T.body, bold: k === 5 || !!c.bold, color: THEME.ink, align: "center" });
          else {
            pen.rect(cx + 0.6, cy, widths[k] - 1.2, rowH - 1.4, c.fill ?? THEME.neutral.cell, 1.4);
            if (lines.length === 1) pen.text(lines[0], cx + widths[k] / 2, cy + (rowH - 1.4 - pen.lh(T.body)) / 2, { size: T.body, bold: !!c.bold, color: c.text === "0" ? THEME.neutral.dim : THEME.ink, align: "center" });
            else {
              const second = lines.slice(1).map(l => l.replace("Risk Score: ", "Risk ").replace("Sentiment: ", "Sentiment ")).join(" · ");
              pen.text(lines[0], cx + widths[k] / 2, cy + 1.2, { size: T.body, bold: true, align: "center" });
              pen.text(second, cx + widths[k] / 2, cy + 1.2 + pen.lh(T.body) + 0.2, { size: 5.8, color: THEME.neutral.strong, align: "center", w: widths[k] - 1.5, maxLines: 1 });
            }
          }
          cx += widths[k];
        });
        cy += rowH;
      });
    });
  };
  // Rows that do not fit on this page continue on the next one with the header repeated.
  let rest = rows;
  let first = true;
  while (rest.length) {
    const fit = Math.max(1, Math.min(rest.length, Math.floor((flow.left - TITLE_H - headH - PAD) / rowH)));
    if (fit < rest.length && fit < 3 && flow.y > CONTENT.y) { flow.newPage(); continue; }
    drawChunk(rest.slice(0, fit), first);
    rest = rest.slice(fit);
    first = false;
    if (rest.length) flow.newPage();
  }
}

// ---------------------------------------------------------------- notes
// Two columns of numbered notes (term on one line, text under it). Shares the previous page when that page is under-filled.
export function drawNotes(ctx: PageCtx) {
  const { pen, flow, model } = ctx;
  const items = model.notes;
  const GUT = 8;
  const colW = (CONTENT.w - 2 * PAD - GUT) / 2;
  const size = T.small + 0.3;
  const itemH = (n: { term: string; text: string }) => pen.lh(size) + pen.measure(n.text, { size, w: colW - 8 }) + 2.2;
  // balance the two columns by height
  const total = items.reduce((a, n) => a + itemH(n), 0);
  const left: typeof items = [], right: typeof items = [];
  let acc = 0;
  for (const n of items) { if (acc + itemH(n) / 2 <= total / 2) { left.push(n); acc += itemH(n); } else right.push(n); }
  const colH = (list: typeof items) => list.reduce((a, n) => a + itemH(n), 0);
  const h = TITLE_H + Math.max(colH(left), colH(right)) + PAD;
  const titleH = pen.measure("Notes and definitions", { size: T.h1, bold: true });
  flow.startSection(titleH + 2 + h);
  sectionTitle(ctx, "Notes and definitions");
  flow.place(Math.min(h, CONTENT.h), y => {
    pen.card(CONTENT.x, y, CONTENT.w, Math.min(h, CONTENT.h));
    const top = cardTitle(pen, CONTENT.x, y, CONTENT.w, "How to read the numbers in this report");
    const drawCol = (list: typeof items, x0: number, startNo: number) => {
      let cy = top;
      list.forEach((n, k) => {
        pen.text(`[${startNo + k}]`, x0, cy, { size, bold: true, color: THEME.accent });
        pen.text(n.term, x0 + 8, cy, { size, bold: true, w: colW - 8, maxLines: 1 });
        cy += pen.lh(size);
        cy += pen.text(n.text, x0 + 8, cy, { size, w: colW - 8 }) + 2.2;
      });
    };
    drawCol(left, CONTENT.x + PAD, 1);
    drawCol(right, CONTENT.x + PAD + colW + GUT, left.length + 1);
  });
}
