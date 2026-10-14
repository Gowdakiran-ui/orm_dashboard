// Draws text the PDF library cannot shape (Devanagari, Tamil, Malayalam, Arabic, Thai, CJK, ...) onto a canvas and
// returns it as a PNG, so the BROWSER does the shaping. The text in the PDF is then an image (not selectable).
// It uses whichever fonts the viewer's system has for those scripts, so a machine without one will draw boxes.

export interface TextImage {
  dataUrl: string;
  // Size in millimetres at the requested font size.
  widthMm: number;
  heightMm: number;
}

export interface TextImageOptions {
  maxWidthMm: number;
  fontSizePt: number;
  bold?: boolean;
  color?: string;
}

const PT_TO_MM = 25.4 / 72;
const SCALE = 4; // canvas pixels per CSS pixel (sharp when printed)
const FONT_STACK = `"Noto Sans", "Nirmala UI", "Mangal", "Noto Sans Devanagari", "Noto Sans Tamil", "Noto Sans Malayalam", "Segoe UI", "Arial Unicode MS", system-ui, sans-serif`;

export function drawTextImage(text: string, o: TextImageOptions): TextImage {
  if (typeof document === "undefined") throw new Error("Cannot draw non-Latin text: no canvas is available in this environment.");
  const px = (o.fontSizePt * PT_TO_MM) * (96 / 25.4); // CSS px for the point size
  const maxPx = (o.maxWidthMm / 25.4) * 96;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Cannot draw non-Latin text: the canvas 2D context is unavailable.");
  const font = `${o.bold ? "700 " : ""}${px}px ${FONT_STACK}`;
  ctx.font = font;

  // Greedy word wrap (spaces), falling back to per-character wrap for unspaced scripts.
  const lines: string[] = [];
  for (const para of text.split("\n")) {
    let line = "";
    const tokens = para.split(/(\s+)/);
    for (const tok of tokens) {
      if (ctx.measureText(line + tok).width <= maxPx || line === "") {
        line += tok;
        while (ctx.measureText(line).width > maxPx && line.length > 1) {
          let cut = line.length - 1;
          while (cut > 1 && ctx.measureText(line.slice(0, cut)).width > maxPx) cut--;
          lines.push(line.slice(0, cut));
          line = line.slice(cut);
        }
      } else {
        lines.push(line.trimEnd());
        line = tok.trimStart();
      }
    }
    lines.push(line.trimEnd());
  }
  const lineH = px * 1.35;
  const widest = Math.max(1, ...lines.map(l => ctx.measureText(l).width));
  canvas.width = Math.ceil(widest * SCALE);
  canvas.height = Math.ceil(lines.length * lineH * SCALE);
  const c2 = canvas.getContext("2d")!;
  c2.scale(SCALE, SCALE);
  c2.font = font;
  c2.fillStyle = o.color ?? "#111827";
  c2.textBaseline = "top";
  lines.forEach((l, k) => c2.fillText(l, 0, k * lineH + (lineH - px) / 2));
  return {
    dataUrl: canvas.toDataURL("image/png"),
    widthMm: (widest / 96) * 25.4,
    heightMm: ((lines.length * lineH) / 96) * 25.4,
  };
}
