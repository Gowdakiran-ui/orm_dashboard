// Every date the UI shows is written DD-MM-YYYY (India). Display only: nothing here changes stored data.
// Built from Intl parts so the order never depends on the viewer's browser locale.
const parts = (d: Date, opts: Intl.DateTimeFormatOptions): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const p of new Intl.DateTimeFormat("en-GB", opts).formatToParts(d)) out[p.type] = p.value;
  return out;
};

export function toDate(input: string | number | Date | null | undefined): Date | null {
  if (input === null || input === undefined || input === "") return null;
  const d = input instanceof Date ? input : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

const DATE_OPTS: Intl.DateTimeFormatOptions = { day: "2-digit", month: "2-digit", year: "numeric" };

/** 20-10-2026 */
export function formatDMY(input: string | number | Date | null | undefined, fallback = "N/A"): string {
  const d = toDate(input);
  if (!d) return fallback;
  const p = parts(d, DATE_OPTS);
  return `${p.day}-${p.month}-${p.year}`;
}

/** 20-10-2026, 09:11 AM */
export function formatDMYTime(input: string | number | Date | null | undefined, fallback = "N/A"): string {
  const d = toDate(input);
  if (!d) return fallback;
  const p = parts(d, { ...DATE_OPTS, hour: "2-digit", minute: "2-digit", hour12: true });
  return `${p.day}-${p.month}-${p.year}, ${p.hour}:${p.minute} ${(p.dayPeriod || "").toUpperCase()}`.trim();
}

/** 20-10 (chart axis labels, where the year would crowd the axis) */
export function formatDM(input: string | number | Date | null | undefined, fallback = "N/A"): string {
  const d = toDate(input);
  if (!d) return fallback;
  const p = parts(d, { day: "2-digit", month: "2-digit" });
  return `${p.day}-${p.month}`;
}

/** 20-10, 09 AM (chart points that carry an hour) */
export function formatDMHour(input: string | number | Date | null | undefined, fallback = "N/A"): string {
  const d = toDate(input);
  if (!d) return fallback;
  const p = parts(d, { day: "2-digit", month: "2-digit", hour: "2-digit", hour12: true });
  return `${p.day}-${p.month}, ${p.hour} ${(p.dayPeriod || "").toUpperCase()}`.trim();
}
