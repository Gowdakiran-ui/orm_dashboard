// Captures Recharts SVGs from an offscreen, already-mounted container as PNGs for the PDF report.
// Colors, fonts and strokes are copied onto each SVG element as inline styles first (CSS variables and
// stylesheets do not survive serialisation), and the capture only starts once the SVG has stopped changing
// (Recharts animates its bars/lines/area). A blank capture is an error, never a silent empty picture.
import type { ChartId } from "@/utils/reportModel";
import type { ChartImage } from "@/lib/exportReport";

export interface WantedChart { id: ChartId; title: string }

// What each chart draws, so "stable" also means "actually drew the data".
const DRAWN: Record<ChartId, string> = {
  sentiment: ".recharts-pie-sector, .recharts-sector",
  topics: ".recharts-bar-rectangle",
  repHistory: ".recharts-line-curve, .recharts-line-dot, .recharts-dot",
  alerts: ".recharts-area-area, .recharts-reference-dot",
};

const STYLE_PROPS = [
  "fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
  "opacity", "font-family", "font-size", "font-weight", "font-style", "text-anchor", "dominant-baseline", "letter-spacing", "visibility",
];

const SCALE = 2;
const STABLE_FRAMES = 12;
const TIMEOUT_MS = 40000; // chart animations are ~1s on a normal screen; slow or busy machines get far longer before this fails
// A hidden tab does not run animation frames (Recharts' animations would not finish), so the capture waits for the tab to be shown.
const HIDDEN_GRACE_MS = 90000;

// requestAnimationFrame, with a timer fallback so a hidden tab can never leave the export waiting forever.
const nextFrame = () => new Promise<void>(r => { let done = false; const fin = () => { if (!done) { done = true; r(); } }; requestAnimationFrame(fin); setTimeout(fin, 250); });

function findCard(root: HTMLElement, title: string): HTMLElement | null {
  const hit = Array.from(root.querySelectorAll<HTMLElement>("*")).find(
    el => el.children.length <= 2 && (el.textContent || "").trim().startsWith(title) && !!el.closest("[class*='rounded-3xl']")
  );
  return (hit?.closest("[class*='rounded-3xl']") as HTMLElement | null) ?? null;
}

async function waitStable(svg: SVGSVGElement, drawn: string, title: string): Promise<void> {
  let visibleMs = 0;
  const start = performance.now();
  let last = "";
  let same = 0;
  while (visibleMs < TIMEOUT_MS && performance.now() - start < HIDDEN_GRACE_MS) {
    const t = performance.now();
    await nextFrame();
    if (document.visibilityState === "hidden") { same = 0; continue; }
    visibleMs += performance.now() - t;
    const now = svg.outerHTML;
    same = now === last ? same + 1 : 0;
    last = now;
    // Stable AND the data series is in the SVG. Stable but empty keeps waiting until the timeout.
    if (same >= STABLE_FRAMES && svg.querySelector(drawn)) return;
  }
  throw new Error(document.visibilityState === "hidden"
    ? `The "${title}" chart could not be captured because this tab was in the background. Keep it in the foreground while the report is prepared.`
    : `The "${title}" chart did not finish drawing (it never became stable, or drew no data).`);
}

function inlineStyles(src: Element, dst: Element) {
  const cs = window.getComputedStyle(src);
  const pieces: string[] = [];
  for (const p of STYLE_PROPS) {
    const v = cs.getPropertyValue(p);
    if (v) pieces.push(`${p}:${v}`);
  }
  if (pieces.length) dst.setAttribute("style", pieces.join(";"));
  const sk = src.children, dk = dst.children;
  for (let i = 0; i < sk.length; i++) if (dk[i]) inlineStyles(sk[i], dk[i]);
}

async function toPng(svg: SVGSVGElement, title: string): Promise<ChartImage> {
  const rect = svg.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const clone = svg.cloneNode(true) as SVGSVGElement;
  inlineStyles(svg, clone);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const xml = new XMLSerializer().serializeToString(clone);
  const img = new Image();
  // A data: URL (the page's CSP img-src allows 'self' data:, not blob:).
  const loaded = new Promise<void>((res, rej) => {
    img.onload = () => res();
    img.onerror = () => rej(new Error(`The "${title}" chart could not be converted to an image.`));
  });
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`;
  await loaded;
  const canvas = document.createElement("canvas");
  canvas.width = width * SCALE;
  canvas.height = height * SCALE;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas is unavailable, so charts cannot be captured.");
  ctx.fillStyle = "#FFFFFF";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  // Blank check: a chart with data always has plenty of non-white pixels.
  const px = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  let inked = 0;
  for (let i = 0; i < px.length; i += 4) if (px[i] < 245 || px[i + 1] < 245 || px[i + 2] < 245) inked++;
  if (inked < 400) throw new Error(`The "${title}" chart was captured blank.`);
  return { dataUrl: canvas.toDataURL("image/png"), width, height };
}

export async function captureCharts(root: HTMLElement, wanted: WantedChart[]): Promise<Partial<Record<ChartId, ChartImage>>> {
  const out: Partial<Record<ChartId, ChartImage>> = {};
  for (const w of wanted) {
    // Recharts' ResponsiveContainer only creates the SVG after it has measured its box, so wait for it to appear.
    let svg: SVGSVGElement | null = null;
    const start = performance.now();
    while (!svg && performance.now() - start < TIMEOUT_MS) {
      svg = findCard(root, w.title)?.querySelector<SVGSVGElement>("svg.recharts-surface") ?? null;
      if (!svg) await nextFrame();
    }
    if (!svg) throw new Error(`The "${w.title}" chart was not found on the export stage.`);
    await waitStable(svg, DRAWN[w.id], w.title);
    out[w.id] = await toPng(svg, w.title);
  }
  return out;
}
