// Turns a ReportModel (utils/reportModel.ts) plus the captured chart images into a PDF. This file and its
// libraries (jspdf, jspdf-autotable) are only ever loaded by a dynamic import() when someone clicks Export Report.
import type { Block, Cell, ChartId, ReportModel } from "@/utils/reportModel";
import { needsShaping } from "@/utils/reportText";
import { drawTextImage, type TextImage, type TextImageOptions } from "@/lib/reportTextImage";

export interface ChartImage { dataUrl: string; width: number; height: number }

export interface RenderDeps {
  // The Noto Sans font file (public/fonts/NotoSans-VF.ttf, same origin).
  loadFont: () => Promise<ArrayBuffer>;
  // Draws text the PDF library cannot shape as an image (needs a browser canvas).
  textImage: (text: string, o: TextImageOptions) => TextImage;
}

export const FONT_URL = "/fonts/NotoSans-VF.ttf";

const defaultDeps: RenderDeps = {
  loadFont: async () => {
    const res = await fetch(FONT_URL);
    if (!res.ok) throw new Error(`Could not load the report font (${FONT_URL}: HTTP ${res.status}).`);
    return res.arrayBuffer();
  },
  textImage: drawTextImage,
};

const FONT = "NotoSans";
const M = 15; // page margin, mm
const TOP = 20; // content starts below the running header
const BOTTOM = 16; // content stops above the running footer
const INK = "#111827";
const MUTED = "#6B7280";
const ACCENT = "#1D4ED8";
const RULE = "#D1D5DB";

function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

const cellOf = (c: Cell) => (typeof c === "string" ? { text: c } : c);

export async function renderReportPdf(
  model: ReportModel,
  charts: Partial<Record<ChartId, ChartImage>>,
  deps: Partial<RenderDeps> = {}
): Promise<Blob> {
  const d: RenderDeps = { ...defaultDeps, ...deps };
  const [{ jsPDF }, autoTableModule] = await Promise.all([import("jspdf"), import("jspdf-autotable")]);
  const autoTable = (autoTableModule as any).default ?? (autoTableModule as any).autoTable;
  const fontB64 = toBase64(await d.loadFont());

  const doc = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait", compress: true });
  doc.addFileToVFS("NotoSans-VF.ttf", fontB64);
  // One variable-font file; PDF text uses its default (Regular) instance. Headings are emboldened by stroking.
  doc.addFont("NotoSans-VF.ttf", FONT, "normal");
  doc.addFont("NotoSans-VF.ttf", FONT, "bold");
  doc.setFont(FONT, "normal");
  doc.setProperties({ title: `${model.meta.title}: ${model.meta.clientName}`, subject: "Brand Equity, Risk Center and Executive Analytics", author: "XOOP", creator: "XOOP dashboard" });
  doc.setLanguage("en-US");

  let landscape = false;
  const pageW = () => (landscape ? 297 : 210);
  const pageH = () => (landscape ? 210 : 297);
  const contentW = () => pageW() - 2 * M;
  let y = TOP;

  const newPage = (toLandscape: boolean) => {
    landscape = toLandscape;
    doc.addPage("a4", toLandscape ? "landscape" : "portrait");
    y = TOP;
  };
  const ensure = (h: number) => { if (y + h > pageH() - BOTTOM) newPage(landscape); };
  const color = (hex: string) => doc.setTextColor(hex);

  // Writes text in the PDF font, or as an image when the text needs shaping. Returns the height used (mm).
  function put(text: string, o: { x?: number; w?: number; size: number; bold?: boolean; color?: string; lineGap?: number; draw?: boolean }): number {
    const x = o.x ?? M;
    const w = o.w ?? contentW() - (x - M);
    const hex = o.color ?? INK;
    if (needsShaping(text)) {
      const img = d.textImage(text, { maxWidthMm: w, fontSizePt: o.size, bold: o.bold, color: hex });
      if (o.draw !== false) {
        ensure(img.heightMm);
        doc.addImage(img.dataUrl, "PNG", x, y, img.widthMm, img.heightMm);
        y += img.heightMm;
      }
      return img.heightMm;
    }
    doc.setFontSize(o.size);
    color(hex);
    const lines: string[] = doc.splitTextToSize(text, w);
    const lh = o.size * 0.3528 * (o.lineGap ?? 1.35);
    if (o.draw === false) return lines.length * lh;
    for (const line of lines) {
      ensure(lh);
      if (o.bold) {
        doc.setDrawColor(hex);
        doc.setLineWidth(0.18);
        doc.text(line, x, y + o.size * 0.3528, { renderingMode: "fillThenStroke" });
      } else {
        doc.text(line, x, y + o.size * 0.3528);
      }
      y += lh;
    }
    return lines.length * lh;
  }

  const gap = (mm: number) => { y += mm; };

  // ---- Cover ----
  put(model.meta.title, { size: 12, color: MUTED });
  gap(6);
  put(model.meta.clientName, { size: 26, bold: true, color: ACCENT });
  gap(3);
  put("Brand Equity · Risk Center · Executive Analytics", { size: 11, color: MUTED });
  gap(12);
  const coverRows: [string, string][] = [["Generated", model.meta.generatedAt]];
  if (model.meta.userEmail) coverRows.push(["Prepared for", model.meta.userEmail]);
  for (const [k, v] of coverRows) {
    put(k, { size: 9, color: MUTED });
    put(v, { size: 11 });
    gap(3);
  }
  gap(3);
  put("Data window", { size: 9, color: MUTED });
  for (const line of model.meta.dataWindow) put(line, { size: 10 });
  gap(8);
  put("How to read this report", { size: 11, bold: true });
  gap(2);
  const TERM_W = 36;
  for (const g of model.meta.guide) {
    const top = y;
    const termH = put(g.term, { w: TERM_W - 2, size: 8.5, bold: true });
    y = top;
    const textH = put(g.text, { x: M + TERM_W, w: contentW() - TERM_W, size: 8.5 });
    y = top + Math.max(termH, textH) + 2;
  }

  // ---- Blocks ----
  // Which page orientation a block belongs on: wide tables are landscape, and the headings and notes that introduce or
  // close such a table stay on its page; everything else is portrait.
  const orient = (blocks: Block[], k: number): boolean => {
    const b = blocks[k];
    if (!b) return false;
    if (b.type === "table") return !!b.landscape;
    const next = blocks[k + 1], prev = blocks[k - 1];
    if (b.type === "heading") return orient(blocks, k + 1);
    if (b.type === "text") return (next?.type === "table" && !!next.landscape) || (prev?.type === "table" && !!prev.landscape);
    return false;
  };

  const sectionBlocks = (blocks: Block[]) => {
    for (let k = 0; k < blocks.length; k++) {
      const b = blocks[k];
      const want = orient(blocks, k);
      if (want !== landscape) newPage(want);
      if (b.type === "heading") {
        gap(b.level === 2 ? 5 : 3);
        // Keep a heading with what follows it: a chart (a few blocks later) needs most of a page's height.
        ensure(blocks.slice(k + 1, k + 4).some(x => x.type === "chart") ? 100 : 30);
        put(b.text, { size: b.level === 2 ? 14 : 11, bold: true, color: b.level === 2 ? ACCENT : INK });
        gap(1.5);
      } else if (b.type === "text") {
        const style = b.style ?? "normal";
        put(b.text, { size: style === "normal" || style === "bold" ? 9.5 : 8.5, bold: style === "bold", color: style === "muted" || style === "note" ? MUTED : INK });
        gap(1.5);
      } else if (b.type === "stats") {
        const perRow = b.items.length >= 5 ? 3 : 2;
        const boxW = (contentW() - (perRow - 1) * 3) / perRow;
        for (let k = 0; k < b.items.length; k += perRow) {
          const row = b.items.slice(k, k + perRow);
          const heights = row.map(it => 4 + put(it.label, { w: boxW - 6, size: 7.5, color: MUTED, draw: false }) + 7 + (it.sub ? put(it.sub, { w: boxW - 6, size: 7.5, color: MUTED, draw: false }) : 0) + 2);
          const h = Math.max(...heights);
          ensure(h + 3);
          row.forEach((it, c) => {
            const x = M + c * (boxW + 3);
            doc.setDrawColor(RULE);
            doc.setLineWidth(0.2);
            doc.roundedRect(x, y, boxW, h, 1.5, 1.5);
            const top = y;
            y = top + 2.5;
            const lh = put(it.label, { x: x + 3, w: boxW - 6, size: 7.5, color: MUTED });
            void lh;
            put(it.value, { x: x + 3, w: boxW - 6, size: 15, bold: true });
            if (it.sub) put(it.sub, { x: x + 3, w: boxW - 6, size: 7.5, color: MUTED });
            y = top;
          });
          y += h + 3;
        }
      } else if (b.type === "alert") {
        const a = b.alert;
        const needs = 28;
        ensure(needs);
        const top = y;
        put(`${a.severity}  ·  ${a.title}`, { x: M + 3, w: contentW() - 3, size: 9.5, bold: true });
        put(`${a.alertType}  ·  raised ${a.raised}`, { x: M + 3, w: contentW() - 3, size: 8, color: MUTED });
        if (a.what !== null) {
          gap(1);
          put("Why this was flagged", { x: M + 3, size: 7.5, color: MUTED });
          put(a.what, { x: M + 3, w: contentW() - 3, size: 9 });
          put("When", { x: M + 3, size: 7.5, color: MUTED });
          put(a.when ?? "Unknown", { x: M + 3, w: contentW() - 3, size: 9 });
          put("Suggested next step (AI-generated)", { x: M + 3, size: 7.5, color: MUTED });
          put(a.nextStep ?? "", { x: M + 3, w: contentW() - 3, size: 9 });
        } else {
          put("Suggested next step not yet generated for this alert.", { x: M + 3, size: 8.5, color: MUTED });
        }
        doc.setDrawColor(a.severity === "CRITICAL" ? "#DC2626" : a.severity === "HIGH" ? "#EA580C" : "#CA8A04");
        doc.setLineWidth(0.9);
        doc.line(M, top, M, y);
        gap(4);
      } else if (b.type === "chart") {
        const img = charts[b.id];
        if (!img) throw new Error(`The "${b.title}" chart was not captured.`);
        const w = Math.min(contentW(), 150);
        const h = (w * img.height) / img.width;
        // The caption stays with its chart: both fit on this page or both move to the next.
        ensure(h + 4 + put(b.caption, { size: 8, draw: false }));
        doc.addImage(img.dataUrl, "PNG", M, y, w, h, undefined, "FAST");
        y += h + 1.5;
        put(b.caption, { size: 8, color: MUTED });
        gap(2);
      } else if (b.type === "table") {
        const avail = contentW();
        const sum = (b.widths ?? b.columns.map(() => 1)).reduce((s, v) => s + v, 0);
        const columnStyles: Record<number, any> = {};
        b.columns.forEach((_, ci) => { columnStyles[ci] = { cellWidth: ((b.widths?.[ci] ?? 1) / sum) * avail }; });
        const fs = b.compact ? 7.5 : 8.5;
        const body = b.rows.map(r => r.map((c, ci) => {
          const cc = cellOf(c);
          const styles: Record<string, any> = {};
          if (cc.fill) styles.fillColor = cc.fill;
          if (cc.color) styles.textColor = cc.color;
          if (cc.align) styles.halign = cc.align;
          if (cc.bold) styles.fontStyle = "bold";
          if (needsShaping(cc.text)) {
            const wMm = (columnStyles[ci]?.cellWidth ?? 40) - 3.2;
            const img = d.textImage(cc.text, { maxWidthMm: wMm, fontSizePt: fs, bold: cc.bold, color: cc.color ?? INK });
            return { content: "", styles: { ...styles, minCellHeight: img.heightMm + 3.2 }, _img: img };
          }
          return { content: cc.text, styles };
        }));
        autoTable(doc, {
          startY: y,
          head: [b.columns],
          body,
          theme: "grid",
          margin: { top: TOP, bottom: BOTTOM, left: M, right: M },
          styles: { font: FONT, fontSize: fs, cellPadding: 1.6, textColor: INK, lineColor: RULE, lineWidth: 0.1, overflow: "linebreak", valign: "middle" },
          headStyles: { fillColor: "#E5E7EB", textColor: INK, fontStyle: "bold", halign: "center" },
          columnStyles,
          rowPageBreak: "avoid",
          showHead: "everyPage",
          didDrawCell: (data: any) => {
            const img: TextImage | undefined = data.cell.raw?._img;
            if (img && data.section === "body") {
              doc.addImage(img.dataUrl, "PNG", data.cell.x + 1.6, data.cell.y + 1.6, img.widthMm, img.heightMm);
            }
          },
        });
        y = ((doc as any).lastAutoTable?.finalY ?? y) + 4;
      }
    }
  };

  for (const section of model.sections) {
    newPage(false);
    put(section.title, { size: 19, bold: true, color: ACCENT });
    gap(2);
    doc.setDrawColor(ACCENT);
    doc.setLineWidth(0.5);
    doc.line(M, y, pageW() - M, y);
    gap(3);
    sectionBlocks(section.blocks);
  }

  newPage(false);
  put("Notes", { size: 14, bold: true, color: ACCENT });
  gap(2);
  model.footnotes.forEach((f, k) => { put(`${k + 1}. ${f}`, { size: 8.5, color: INK }); gap(1.5); });

  // Running header and footer on every page except the cover.
  const total = doc.getNumberOfPages();
  for (let p = 2; p <= total; p++) {
    doc.setPage(p);
    const w = doc.internal.pageSize.getWidth();
    const h = doc.internal.pageSize.getHeight();
    doc.setFont(FONT, "normal");
    doc.setFontSize(8);
    doc.setTextColor(MUTED);
    // Non-Latin client names are drawn as an image in the body only; the running header uses the file-safe ASCII/Latin text.
    const headerName = needsShaping(model.meta.clientName) ? "" : ` · ${model.meta.clientName}`;
    doc.text(`XOOP | Reputation Report${headerName}`, M, 11);
    doc.setDrawColor(RULE);
    doc.setLineWidth(0.2);
    doc.line(M, 13, w - M, 13);
    doc.text(`Generated ${model.meta.generatedAt}`, M, h - 8);
    doc.text(`Page ${p} of ${total}`, w - M, h - 8, { align: "right" });
  }
  doc.setPage(1);
  return doc.output("blob");
}
