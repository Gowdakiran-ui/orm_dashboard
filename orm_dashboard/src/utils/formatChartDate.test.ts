import { describe, it, expect } from "vitest";
import { formatChartDate } from "./formatChartDate";

describe("formatChartDate", () => {
  it("returns 'N/A' for null", () => {
    expect(formatChartDate(null)).toBe("N/A");
  });

  it("returns 'N/A' for undefined", () => {
    expect(formatChartDate(undefined)).toBe("N/A");
  });

  it("returns 'N/A' for an empty string", () => {
    expect(formatChartDate("")).toBe("N/A");
  });

  it("returns 'Invalid Date' for an unparseable date string (JS Date does not throw)", () => {
    // `new Date("not-a-date")` doesn't throw -- it produces an Invalid Date
    // object, so formatChartDate's try/catch never triggers here; the N/A
    // fallback is reserved for a genuinely thrown error (or null/undefined).
    expect(formatChartDate("not-a-date")).toBe("Invalid Date");
  });

  it("returns a real (non-fallback) formatted string for a valid ISO date", () => {
    // Exact output is locale/environment-dependent (toLocaleDateString), so this
    // checks the real-formatting contract rather than an exact string match.
    const result = formatChartDate("2026-03-15T00:00:00Z");
    expect(result).not.toBe("N/A");
    expect(typeof result).toBe("string");
    expect(result.length).toBeGreaterThan(0);
  });

  it("includes hour formatting when includeHour is true", () => {
    const withoutHour = formatChartDate("2026-03-15T14:30:00Z", false);
    const withHour = formatChartDate("2026-03-15T14:30:00Z", true);
    expect(withHour).not.toBe("N/A");
    expect(withHour).not.toBe(withoutHour);
  });
});
