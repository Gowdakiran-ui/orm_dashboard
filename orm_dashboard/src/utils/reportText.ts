// Text rules for the exported report, shared by the model (what is said) and the renderer (how it is drawn).

// Emoji and their joiners/selectors: removed everywhere in the report (the default PDF fonts cannot draw them).
const EMOJI = /[\p{Extended_Pictographic}\p{Regional_Indicator}\u{FE0E}\u{FE0F}\u{200D}\u{20E3}\u{E0020}-\u{E007F}]/gu;

export function stripEmoji(text: string | null | undefined): string {
  if (!text) return "";
  return text.replace(EMOJI, "").replace(/[ \t]{2,}/g, " ").trim();
}

// What the bundled Noto Sans can draw: Latin, IPA/modifiers, combining marks, Greek, Cyrillic, Latin Extended
// Additional, Greek Extended, general punctuation, currency signs (incl. the rupee sign U+20B9), letterlike
// symbols, arrows and maths operators. Anything else is a script the PDF library cannot shape (Devanagari,
// Tamil, Malayalam, Arabic, Thai, ...) or a glyph the font lacks (CJK): such text is drawn as an image by the
// browser, which does the shaping, instead of being written as PDF text.
const SUPPORTED = /^[\u0000-ԯḀ-῿ -⃏℀-⅏←-⇿∀-⋿ ]*$/;

export function needsShaping(text: string | null | undefined): boolean {
  return !!text && !SUPPORTED.test(text);
}

// ---- IST (Asia/Kolkata) ------------------------------------------------------------------------------
const IST = "Asia/Kolkata";

function parse(v: string | Date | null | undefined): Date | null {
  if (!v) return null;
  const d = v instanceof Date ? v : new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

const dateTimeFmt = new Intl.DateTimeFormat("en-GB", { timeZone: IST, day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });
const dateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: IST, day: "numeric", month: "short", year: "numeric" });
const keyFmt = new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" });

// "2 Oct 2026, 8:32 pm IST"; null when the value is missing or not a date.
export function formatIST(v: string | Date | null | undefined): string | null {
  const d = parse(v);
  return d ? `${dateTimeFmt.format(d).replace(/\bam\b/, "AM").replace(/\bpm\b/, "PM")} IST` : null;
}

// "2 Oct 2026 IST"
export function formatISTDate(v: string | Date | null | undefined): string | null {
  const d = parse(v);
  return d ? `${dateFmt.format(d)} IST` : null;
}

// "2026-10-02", the IST calendar day (used for the file name).
export function istDateKey(v: string | Date | null | undefined): string | null {
  const d = parse(v);
  return d ? keyFmt.format(d) : null;
}
