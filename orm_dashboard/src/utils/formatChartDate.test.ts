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

  it("returns 'N/A' for an unparseable date string", () => {
    expect(formatChartDate("not-a-date")).toBe("N/A");
  });

  it("is day-month (DD-MM), with the hour when asked", () => {
    expect(formatChartDate(new Date(2026, 8, 4, 16).toISOString())).toBe("04-09");
    expect(formatChartDate(new Date(2026, 8, 4, 16).toISOString(), true)).toBe("04-09, 04 PM");
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
