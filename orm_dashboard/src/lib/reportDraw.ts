// Drawing primitives and the page-flow engine for the PDF report. Colours, sizes and margins come from reportTheme.ts.
// Text goes through Pen.text(), which writes PDF text in Noto Sans, or draws it as an image (reportTextImage.ts) when the
// text needs shaping (Devanagari, Tamil, ...). Layout is measured first (Pen.measure*) and placed second, so a card is
// never split across pages and its height is known before it is drawn.
import type { jsPDF } from "jspdf";
import { needsShaping } from "@/utils/reportText";
import type { TextImage, TextImageOptions } from "@/lib/reportTextImage";
import { CONTENT, FONT_FAMILY, MIN_FILL, PAGE, THEME } from "@/lib/reportTheme";

const PT = 0.3528; // mm per point

export interface TextOpts {
  size: number;
  bold?: boolean;
  color?: string;
  w?: number;
  align?: "left" | "center" | "right";
  maxLines?: number;
  lineHeight?: number;
  charSpace?: number;
}

export class Pen {
  constructor(public doc: jsPDF, private textImage: (text: string, o: TextImageOptions) => TextImage) {}

  private setFont(size: number, bold?: boolean) {
    this.doc.setFont(FONT_FAMILY, bold ? "bold" : "normal");
    this.doc.setFontSize(size);
  }

  lh(size: number, factor?: number) { return size * PT * (factor ?? THEME.lineHeight); }

  width(text: string, size: number, bold?: boolean): number {
    if (needsShaping(text)) return this.textImage(text, { maxWidthMm: 1000, fontSizePt: size, bold }).widthMm;
    this.setFont(size, bold);
    return this.doc.getTextWidth(text);
  }

  // Wrapped lines, cut to maxLines with an ellipsis on the last kept line.
  lines(text: string, w: number, size: number, bold?: boolean, maxLines?: number): string[] {
    this.setFont(size, bold);
    const all: string[] = this.doc.splitTextToSize(text, w);
    if (!maxLines || all.length <= maxLines) return all;
    const kept = all.slice(0, maxLines);
    let last = kept[maxLines - 1].trimEnd();
    while (last.length > 1 && this.doc.getTextWidth(`${last}…`) > w) last = last.slice(0, -1).trimEnd();
    kept[maxLines - 1] = `${last}…`;
    return kept;
  }

  // Height in mm that text() would use.
  measure(text: string, o: TextOpts): number {
    const w = o.w ?? 1000;
    if (needsShaping(text)) return this.shaped(text, o, w).heightMm;
    return this.lines(text, w, o.size, o.bold, o.maxLines).length * this.lh(o.size, o.lineHeight);
  }

  private shaped(text: string, o: TextOpts, w: number): TextImage {
    let t = text;
    let img = this.textImage(t, { maxWidthMm: w, fontSizePt: o.size, bold: o.bold, color: o.color ?? THEME.ink });
    if (o.maxLines) {
      const cap = o.maxLines * this.lh(o.size, o.lineHeight) * 1.08;
      while (img.heightMm > cap && t.length > 2) {
        t = `${t.slice(0, Math.max(1, Math.floor(t.length * 0.85))).trimEnd()}…`;
        img = this.textImage(t, { maxWidthMm: w, fontSizePt: o.size, bold: o.bold, color: o.color ?? THEME.ink });
      }
    }
    return img;
  }

  // Draws text with its TOP at y. Returns the height used.
  text(text: string, x: number, y: number, o: TextOpts): number {
    const w = o.w ?? 1000;
    const align = o.align ?? "left";
    const color = o.color ?? THEME.ink;
    if (needsShaping(text)) {
      const img = this.shaped(text, o, w);
      const ix = align === "right" ? x - img.widthMm : align === "center" ? x - img.widthMm / 2 : x;
      this.doc.addImage(img.dataUrl, "PNG", ix, y, img.widthMm, img.heightMm);
      return img.heightMm;
    }
    const lines = this.lines(text, w, o.size, o.bold, o.maxLines);
    this.setFont(o.size, o.bold);
    this.doc.setTextColor(color);
    const step = this.lh(o.size, o.lineHeight);
    lines.forEach((line, k) => {
      const opts: Record<string, unknown> = { baseline: "top", align };
      if (o.charSpace) opts.charSpace = o.charSpace;
      this.doc.text(line, x, y + k * step + (step - o.size * PT) / 2, opts as never);
    });
    return lines.length * step;
  }

  card(x: number, y: number, w: number, h: number, fill: string = THEME.card.fill) {
    const d = this.doc;
    d.setFillColor(fill);
    const border = THEME.card.border;
    if (border) { d.setDrawColor(border); d.setLineWidth(0.25); d.roundedRect(x, y, w, h, THEME.card.radius, THEME.card.radius, "FD"); }
    else d.roundedRect(x, y, w, h, THEME.card.radius, THEME.card.radius, "F");
  }

  rect(x: number, y: number, w: number, h: number, fill: string, radius = 0) {
    this.doc.setFillColor(fill);
    if (radius > 0) this.doc.roundedRect(x, y, w, h, radius, radius, "F"); else this.doc.rect(x, y, w, h, "F");
  }

  line(x1: number, y1: number, x2: number, y2: number, color: string, width = 0.25) {
    this.doc.setDrawColor(color);
    this.doc.setLineWidth(width);
    this.doc.line(x1, y1, x2, y2);
  }

  // A small rounded label. Returns its width.
  pill(text: string, x: number, y: number, o: { fill: string; color?: string; size?: number; h?: number }): number {
    const size = o.size ?? THEME.type.tiny;
    const h = o.h ?? 4.4;
    const w = this.width(text, size, true) + 4;
    this.rect(x, y, w, h, o.fill, h / 2);
    this.text(text, x + w / 2, y + (h - size * PT * THEME.lineHeight) / 2, { size, bold: true, color: o.color ?? THEME.neutral.white, align: "center" });
    return w;
  }

  // Section heading on the page background (white on blue).
  heading(text: string, x: number, y: number, sub?: string): number {
    const hs = THEME.type.h1;
    const onPage = THEME.page.headerInk;
    let h = this.text(text, x, y, { size: hs, bold: true, color: THEME.page.headerBand !== null ? THEME.blue.deep : onPage });
    if (sub) {
      const subColor = THEME.page.headerBand !== null ? THEME.muted : THEME.page.headerMuted;
      h += this.text(sub, x, y + h, { size: THEME.type.body, color: subColor, w: CONTENT.w });
    }
    return h;
  }
}

export interface RowCell {
  span: number; // columns of 12
  measure: (w: number) => number;
  draw: (x: number, y: number, w: number, h: number) => void;
}

// Places things top to bottom on landscape A4 pages and records how full every page is.
export class Flow {
  y = CONTENT.y;
  page = 1;
  extent = new Map<number, number>(); // page -> lowest used y
  private painted = new Set<number>();

  constructor(public pen: Pen, private paintPage: (page: number) => void) {
    this.painted.add(1);
    this.paintPage(1);
    this.extent.set(1, CONTENT.y);
  }

  get doc() { return this.pen.doc; }
  get left() { return CONTENT.bottom - this.y; }
  // Share of the printable height used on the current page.
  get fill() { return (this.y - CONTENT.y) / CONTENT.h; }

  newPage() {
    this.doc.addPage(PAGE.format, PAGE.orientation);
    this.page = this.doc.getNumberOfPages();
    this.markPainted(this.page);
    this.y = CONTENT.y;
    this.extent.set(this.page, CONTENT.y);
  }

  // Called when another library (autoTable) added a page: paint it like any other.
  markPainted(page: number) {
    if (this.painted.has(page)) return;
    this.painted.add(page);
    this.paintPage(page);
  }

  noteExtent(page: number, y: number) { this.extent.set(page, Math.max(this.extent.get(page) ?? 0, y)); }

  ensure(h: number) { if (h > this.left) this.newPage(); }

  // A new section starts on this page only when the page is not yet well filled and the section's first block fits;
  // otherwise it starts a fresh page (so small sections share a page, and full pages are never squeezed).
  startSection(firstBlockH: number) {
    if (this.y > CONTENT.y && (this.fill >= MIN_FILL || firstBlockH > this.left)) this.newPage();
  }

  place(h: number, draw: (y: number) => void) {
    this.ensure(h);
    draw(this.y);
    this.noteExtent(this.page, this.y + h);
    this.y += h + PAGE.rowGap;
  }

  // Equal-height cards across the 12-column grid.
  row(cells: RowCell[], minH = 0) {
    const gut = PAGE.gutter;
    const total = cells.reduce((sum, c) => sum + c.span, 0);
    const avail = CONTENT.w - gut * (cells.length - 1);
    const ws = cells.map(c => (avail * c.span) / total);
    const h = Math.max(minH, ...cells.map((c, k) => c.measure(ws[k])));
    this.place(h, y => {
      let x = CONTENT.x;
      cells.forEach((c, k) => { this.pen.card(x, y, ws[k], h); c.draw(x, y, ws[k], h); x += ws[k] + gut; });
    });
    return h;
  }

  gap(mm: number) { this.y += mm; }
}
