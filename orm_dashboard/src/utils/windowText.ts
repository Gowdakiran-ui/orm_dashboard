// The look-back a stored score used, as page text. The engines read it from config (EXEC_WINDOW_DAYS = 365 for executive
// scores, BENCHMARK_WINDOW_DAYS = 90 for competitor benchmarks) and the API sends it as `window_days` on each row; rows
// stored before that setting existed carry no value and used 30 days.
export const DEFAULT_WINDOW_DAYS = 30;

export function windowDays(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.round(value) : DEFAULT_WINDOW_DAYS;
}

/** "12 months" for a year-long window, otherwise "90 days": the look-back as a plain length, without "last". */
export function windowLength(value: unknown): string {
  const d = windowDays(value);
  return d >= 360 && d <= 370 ? "12 months" : `${d} days`;
}

/** "last 90 days" */
export function windowPhrase(value: unknown): string {
  return `last ${windowDays(value)} days`;
}
