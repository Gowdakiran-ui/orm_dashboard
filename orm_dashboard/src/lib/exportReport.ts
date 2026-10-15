// Turns a ReportModel (utils/reportModel.ts) into a PDF: uniform A4 landscape pages, a blue theme (lib/reportTheme.ts),
// cards placed by the flow engine (lib/reportDraw.ts), pages composed in lib/reportPages.ts. Charts are drawn as vectors.
// This file and its libraries (jspdf, jspdf-autotable) are only ever loaded by a dynamic import() when someone clicks
// Export Report.
import type { NoteId, ReportModel } from "@/utils/reportModel";
import { drawTextImage, type TextImage, type TextImageOptions } from "@/lib/reportTextImage";
import { Flow, Pen } from "@/lib/reportDraw";
import { drawAnalyticsHistoryAlerts, drawAnalyticsSentimentTopics, drawBrandEquity, drawCover, drawHeatmap, drawNotes, drawRiskCenter, drawSummary, type PageCtx } from "@/lib/reportPages";
import { CONTENT, FONT_FAMILY, FONT_FILES, PAGE, THEME } from "@/lib/reportTheme";

export interface RenderDeps {
  // The Noto Sans Regular and Bold files (public/fonts, same origin).
  loadFonts: () => Promise<{ regular: ArrayBuffer; bold: ArrayBuffer }>;
  // Draws text the PDF library cannot shape as an image (needs a browser canvas).
  textImage: (text: string, o: TextImageOptions) => TextImage;
}

async function fetchFont(url: string): Promise<ArrayBuffer> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not load the report font (${url}: HTTP ${res.status}).`);
  return res.arrayBuffer();
}

const defaultDeps: RenderDeps = {
  loadFonts: async () => {
    const [regular, bold] = await Promise.all([fetchFont(FONT_FILES.regular), fetchFont(FONT_FILES.bold)]);
    return { regular, bold };
  },
  textImage: drawTextImage,
};

function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

export interface PageStat { page: number; width: number; height: number; fill: number }

export async function renderReportPdfDetailed(model: ReportModel, deps: Partial<RenderDeps> = {}): Promise<{ blob: Blob; pages: PageStat[] }> {
  const d: RenderDeps = { ...defaultDeps, ...deps };
  const [{ jsPDF }, autoTableModule] = await Promise.all([import("jspdf"), import("jspdf-autotable")]);
  const autoTable = (autoTableModule as any).default ?? (autoTableModule as any).autoTable;
  const fonts = await d.loadFonts();

  const doc = new jsPDF({ unit: "mm", format: PAGE.format, orientation: PAGE.orientation, compress: true });
  doc.addFileToVFS("NotoSans-Regular.ttf", toBase64(fonts.regular));
  doc.addFileToVFS("NotoSans-Bold.ttf", toBase64(fonts.bold));
  doc.addFont("NotoSans-Regular.ttf", FONT_FAMILY, "normal");
  doc.addFont("NotoSans-Bold.ttf", FONT_FAMILY, "bold");
  doc.setFont(FONT_FAMILY, "normal");
  doc.setProperties({ title: `${model.meta.title}: ${model.meta.clientName}`, subject: "Brand Equity, Risk Center and Executive Analytics", author: "XOOP", creator: "XOOP dashboard" });
  doc.setLanguage("en-US");

  const pen = new Pen(doc, d.textImage);
  // Every page gets its background when it is created (page 1, the cover, is painted in the cover colour).
  const flow = new Flow(pen, page => {
    const prev = doc.getCurrentPageInfo().pageNumber;
    doc.setPage(page);
    pen.rect(0, 0, PAGE.width, PAGE.height, page === 1 ? THEME.cover.background : THEME.page.background);
    if (page !== 1 && THEME.page.headerBand) pen.rect(0, 0, PAGE.width, PAGE.headerH, THEME.page.headerBand);
    doc.setPage(prev);
  });
  const noteNo = new Map(model.notes.map((n, k) => [n.id, k + 1]));
  const mark = (...ids: NoteId[]) => {
    const nums = [...new Set(ids.map(id => noteNo.get(id)).filter((n): n is number => n !== undefined))].sort((a, b) => a - b);
    return nums.length ? `[${nums.join(",")}]` : undefined;
  };
  const ctx: PageCtx = { pen, flow, model, autoTable, textImage: d.textImage, mark };

  drawCover(ctx);
  flow.extent.set(1, CONTENT.bottom); // full-bleed cover
  flow.newPage();
  drawSummary(ctx);
  // Each section starts on the current page only when that page is under-filled and the section's first blocks fit.
  flow.startSection(60);
  drawBrandEquity(ctx);
  flow.startSection(75);
  drawRiskCenter(ctx);
  flow.startSection(45);
  drawAnalyticsSentimentTopics(ctx);
  flow.startSection(45);
  drawAnalyticsHistoryAlerts(ctx);
  flow.startSection(72);
  drawHeatmap(ctx);
  drawNotes(ctx);

  // Running header and footer on every page except the cover.
  const total = doc.getNumberOfPages();
  for (let p = 2; p <= total; p++) {
    doc.setPage(p);
    pen.rect(PAGE.margin, PAGE.headerH - 1.2, PAGE.width - 2 * PAGE.margin, 0.2, THEME.page.rule);
    pen.rect(PAGE.margin, 5.2, 1.8, 5.2, THEME.accent, 0.4);
    pen.text("XOOP", PAGE.margin + 4, 4.6, { size: 10, bold: true, color: THEME.page.headerInk, charSpace: 1 });
    pen.text(model.meta.clientName, PAGE.width - PAGE.margin, 5, { size: 8.5, color: THEME.page.headerMuted, align: "right", w: 140, maxLines: 1 });
    pen.text(`Generated ${model.meta.generatedAt}`, PAGE.margin, PAGE.height - PAGE.footerH + 3, { size: 7.5, color: THEME.page.footerInk });
    pen.text(`Page ${p} of ${total}`, PAGE.width - PAGE.margin, PAGE.height - PAGE.footerH + 3, { size: 7.5, color: THEME.page.footerInk, align: "right" });
  }
  doc.setPage(1);

  const pages: PageStat[] = [];
  for (let p = 1; p <= total; p++) {
    const size = doc.getPageInfo(p).pageContext.mediaBox;
    const used = flow.extent.get(p) ?? CONTENT.y;
    pages.push({ page: p, width: size.topRightX / 72 * 25.4, height: size.topRightY / 72 * 25.4, fill: Math.max(0, Math.min(1, (used - CONTENT.y) / CONTENT.h)) });
  }
  return { blob: doc.output("blob"), pages };
}

export async function renderReportPdf(model: ReportModel, deps: Partial<RenderDeps> = {}): Promise<Blob> {
  return (await renderReportPdfDetailed(model, deps)).blob;
}
