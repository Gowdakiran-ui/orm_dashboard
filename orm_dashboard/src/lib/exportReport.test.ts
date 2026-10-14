// Renderer smoke test: a fixture model becomes a real PDF (several pages, both orientations, tables, charts, shaped-text images).
import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { renderReportPdf } from "./exportReport";
import { readingGuide, type ReportModel, type Block } from "@/utils/reportModel";

const FONT = readFileSync(path.resolve(__dirname, "../../public/fonts/NotoSans-VF.ttf"));
const loadFont = async () => FONT.buffer.slice(FONT.byteOffset, FONT.byteOffset + FONT.byteLength) as ArrayBuffer;
// 1x1 PNG, enough to exercise addImage.
const PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

const rows = (n: number) => Array.from({ length: n }, (_, i) => [`Headline number ${i} with ₹349 cr and “quotes”`, { text: "33.4", align: "center" as const }, { text: "MEDIUM", fill: "#FDE68A" }, "Feed", "4 Aug 2026, 6:30 PM IST", "Negative", "General"]);
const model = (flaggedRows: number, extra: Block[] = []): ReportModel => ({
  meta: { title: "XOOP | Reputation Report", clientName: "Acme Corp", generatedAt: "14 Oct 2026, 2:07 PM IST", userEmail: "me@example.com", dataWindow: ["Articles: newest 449 of 449"], guide: [{ term: "N/A", text: "Not enough data." }], fileName: "x.pdf" },
  sections: [
    { id: "brand-equity", title: "Brand Equity", blocks: [
      { type: "text", text: "No Critical or High risks flagged.", style: "bold" },
      { type: "stats", items: [{ label: "Reputation Score", value: "75.51", sub: "Grade B" }, { label: "Risk Signals", value: "0" }, { label: "Total", value: "5" }] },
      { type: "text", text: "A long paragraph. ".repeat(60) },
    ] },
    { id: "risk-center", title: "Risk Center", blocks: [
      { type: "heading", level: 3, text: "Flagged Articles" },
      { type: "table", landscape: true, compact: true, columns: ["Headline", "Score", "Severity", "Source", "Date (IST)", "Sentiment", "Topic"], widths: [88, 14, 20, 40, 34, 22, 36], rows: rows(flaggedRows) },
      { type: "alert", alert: { severity: "HIGH", title: "Company: Multi-Signal Incident", alertType: "Multi-Signal Incident", raised: "8 Oct 2026, 4:44 PM IST", what: "what", when: "Oct 08, 2026 11:14 UTC", nextStep: "next" } },
      ...extra,
    ] },
    { id: "executive-analytics", title: "Executive Analytics", blocks: [
      { type: "heading", level: 3, text: "Coverage by Topic" },
      { type: "chart", id: "topics", title: "Coverage by Topic", caption: "Articles per topic." },
    ] },
  ],
  footnotes: ["A footnote.", "Another."],
});
const pages = (blob: Blob) => blob.arrayBuffer().then(b => (Buffer.from(b).toString("latin1").match(/\/Type\s*\/Page\b/g) || []).length);
const charts = { topics: { dataUrl: PNG, width: 520, height: 260 } };

describe("renderReportPdf", () => {
  it("produces a PDF with more than one page, without throwing", async () => {
    const blob = await renderReportPdf(model(40), charts, { loadFont });
    expect(blob.size).toBeGreaterThan(5000);
    const head = Buffer.from(await blob.arrayBuffer()).subarray(0, 5).toString("latin1");
    expect(head).toBe("%PDF-");
    expect(await pages(blob)).toBeGreaterThan(3);
  });
  it("pages large tables instead of cutting them off (more rows, more pages)", async () => {
    const small = await pages(await renderReportPdf(model(5), charts, { loadFont }));
    const big = await pages(await renderReportPdf(model(300), charts, { loadFont }));
    expect(big).toBeGreaterThan(small + 3);
  });
  it("draws text that needs shaping (Devanagari/Tamil) as an image through the shared helper, and only that text", async () => {
    const textImage = vi.fn((_text: string, _o: unknown) => ({ dataUrl: PNG, widthMm: 40, heightMm: 5 }));
    const blob = await renderReportPdf(
      model(3, [{ type: "text", text: "तीन साल बाद फिर अंबानी को पीछे छोड़ देश के नं. 1" }]),
      charts, { loadFont, textImage }
    );
    expect(textImage).toHaveBeenCalled();
    expect(textImage.mock.calls.every(c => /[ऀ-෿]/.test(c[0]))).toBe(true);
    expect(blob.size).toBeGreaterThan(5000);
  });
  it("a table cell with such text is drawn as an image too", async () => {
    const textImage = vi.fn((_text: string, _o: unknown) => ({ dataUrl: PNG, widthMm: 30, heightMm: 5 }));
    const m = model(0);
    (m.sections[1].blocks[1] as any).rows = [["ரூ.6 லட்சம் கோடி முதலீடு", "1", "MEDIUM", "Feed", "d", "Negative", "General"]];
    await renderReportPdf(m, charts, { loadFont, textImage });
    expect(textImage).toHaveBeenCalledTimes(1);
  });
  it("fails loudly when a chart the model asks for was not captured", async () => {
    await expect(renderReportPdf(model(3), {}, { loadFont })).rejects.toThrow(/chart was not captured/);
  });
  it("tags the document language as English", async () => {
    const blob = await renderReportPdf(model(3), charts, { loadFont });
    expect(Buffer.from(await blob.arrayBuffer()).toString("latin1")).toMatch(/\/Lang \(en-US\)/);
  });
  it("the full reading guide fits on the cover page (cover + notes = 2 pages with no sections)", async () => {
    const m = model(0);
    m.sections = [];
    m.meta.guide = readingGuide();
    expect(await pages(await renderReportPdf(m, charts, { loadFont }))).toBe(2);
  });
  it("a chart caption is printed with its chart (the page count does not change when only the caption is added)", async () => {
    const base = model(0);
    const withCap = model(0);
    (withCap.sections[2].blocks[1] as any).caption = "A caption. ".repeat(20);
    expect(await pages(await renderReportPdf(withCap, charts, { loadFont }))).toBe(await pages(await renderReportPdf(base, charts, { loadFont })));
  });
});
