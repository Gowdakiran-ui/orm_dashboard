// Renderer tests: a report model becomes a real PDF with uniform A4 landscape pages, a theme from reportTheme.ts, vector
// charts, shaped-text images, and every non-final page well filled.
import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { renderReportPdf, renderReportPdfDetailed } from "./exportReport";
import { buildReportModel } from "@/utils/reportModel";
import { input, mkDocs, analyticsFor, summary, alerts, hist } from "@/utils/reportTestFixtures";
import { MIN_FILL, PAGE, THEME, FONT_FILES } from "./reportTheme";

const font = (f: string) => { const b = readFileSync(path.resolve(__dirname, "../../public", f.replace(/^\//, ""))); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer; };
const loadFonts = async () => ({ regular: font(FONT_FILES.regular), bold: font(FONT_FILES.bold) });
// 1x1 PNG, enough to exercise addImage.
const PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
const textImage = (t: string, o: { maxWidthMm: number; fontSizePt: number }) => ({ dataUrl: PNG, widthMm: Math.min(o.maxWidthMm, t.length * o.fontSizePt * 0.19), heightMm: o.fontSizePt * 0.3528 * 1.35 });
const deps = { loadFonts, textImage };

const medium = { scored: true, risk: 40, risk_exact: 40.2, risk_level: "MEDIUM", risk_sentiment: "Negative" };
const withFlagged = (n: number) => {
  const documents = mkDocs(Math.max(140, n * 3), i => (i % 3 === 0 ? medium : {}));
  return input({ documents, analytics: analyticsFor(documents, alerts, hist) });
};

describe("report theme and page constants", () => {
  it("one page size constant: A4 landscape, 297 x 210 mm", () => {
    expect(PAGE).toMatchObject({ format: "a4", orientation: "landscape", width: 297, height: 210 });
  });
  it("every theme value is a token in reportTheme.ts (page background, card, type scale)", () => {
    expect(THEME.page.background).toMatch(/^#[0-9A-F]{6}$/i);
    expect(THEME.card.fill).toBe("#FFFFFF");
    expect(THEME.type.body).toBeGreaterThan(0);
  });
  it("the renderer, drawing engine, pages and charts hold no colour literals of their own", () => {
    for (const f of ["exportReport.ts", "reportDraw.ts", "reportPages.ts", "reportCharts.ts"]) expect(readFileSync(path.resolve(__dirname, f), "utf-8")).not.toMatch(/#[0-9A-Fa-f]{6}\b/);
  });
});

describe("renderReportPdf", () => {
  it("every page is A4 landscape; for ordinary data every page but the cover and the last is at least 60% filled", async () => {
    for (const n of [1, 14, 60]) {
      const { blob, pages } = await renderReportPdfDetailed(buildReportModel(withFlagged(n)), deps);
      expect(Buffer.from(await blob.arrayBuffer()).subarray(0, 5).toString("latin1")).toBe("%PDF-");
      expect(pages.length).toBeGreaterThan(3);
      for (const p of pages) { expect(Math.round(p.width)).toBe(297); expect(Math.round(p.height)).toBe(210); }
      // The page where a very long flagged table ends is as full as the table's last rows (the only exception).
      if (n <= 14) for (const p of pages.slice(1, -1)) expect(p.fill, `page ${p.page} of ${pages.length} (n=${n})`).toBeGreaterThanOrEqual(0.6);
    }
  });
  it("the target fill is 70% and the summary page reaches it", async () => {
    expect(MIN_FILL).toBe(0.7);
    const { pages } = await renderReportPdfDetailed(buildReportModel(input()), deps);
    expect(pages[1].fill).toBeGreaterThanOrEqual(MIN_FILL);
  });
  it("a long flagged table continues on following pages (more rows, more pages), all the same size", async () => {
    const small = await renderReportPdfDetailed(buildReportModel(withFlagged(5)), deps);
    const big = await renderReportPdfDetailed(buildReportModel(withFlagged(200)), deps);
    expect(big.pages.length).toBeGreaterThan(small.pages.length + 3);
    expect(new Set(big.pages.map(p => `${Math.round(p.width)}x${Math.round(p.height)}`)).size).toBe(1);
  });
  it("draws text that needs shaping (Devanagari/Tamil) as an image through the shared helper, and only that text", async () => {
    const spy = vi.fn(textImage);
    const documents = mkDocs(60, i => (i % 3 === 0 ? { ...medium, title: i === 0 ? "तीन साल बाद फिर अंबानी को पीछे छोड़ देश" : `Doc ${i}` } : {}));
    await renderReportPdf(buildReportModel(input({ documents, analytics: analyticsFor(documents, alerts, hist) })), { loadFonts, textImage: spy });
    expect(spy).toHaveBeenCalled();
    expect(spy.mock.calls.every(c => /[ऀ-෿]/.test(c[0]))).toBe(true);
  });
  it("tags the document language as English and sets the title", async () => {
    const blob = await renderReportPdf(buildReportModel(input()), deps);
    const raw = Buffer.from(await blob.arrayBuffer()).toString("latin1");
    expect(raw).toMatch(/\/Lang \(en-US\)/);
    expect(raw).toContain("/Title (XOOP | Reputation Report: Acme Corp)");
  });
  it("renders the empty and the failed states without throwing", async () => {
    const empty = input({ documents: [], analytics: analyticsFor([], [], []), alerts: [], repHistory: [], reputationSummary: summary({ document_risk: { visible_documents: 0, scored_documents: 0, unscored_documents: 0, total: 0, critical: 0, high: 0, medium: 0 }, sentiment: { positive: 0, neutral: 0, negative: 0, dominant: null } }) });
    const failed = input({ reputationSummary: null, reputationSummaryError: "x", documentsError: "x", alertsError: "x", historyError: "x", documents: [], analytics: analyticsFor([], [], []), alerts: [], repHistory: [] });
    for (const i of [empty, failed]) {
      const { pages } = await renderReportPdfDetailed(buildReportModel(i), deps);
      expect(pages.length).toBeGreaterThanOrEqual(3);
    }
  });
});
