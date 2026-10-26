import { describe, it, expect } from "vitest";
import { formatDMY, formatDMYTime, formatDM, formatDMHour, toDate } from "./dateFormat";

// Local-time constructor so the test does not depend on the machine's time zone.
const local = (y: number, m: number, d: number, h = 0, min = 0) => new Date(y, m - 1, d, h, min);

describe("DD-MM-YYYY display", () => {
  it("day first, zero padded, four-digit year", () => {
    expect(formatDMY(local(2026, 10, 7))).toBe("07-10-2026");
    expect(formatDMY(local(2026, 1, 31))).toBe("31-01-2026");
  });
  it("US-style ambiguity is gone: 3 Oct is 03-10, never 10-03", () => {
    expect(formatDMY(local(2026, 10, 3))).toBe("03-10-2026");
  });
  it("date with time, 12-hour clock", () => {
    expect(formatDMYTime(local(2026, 10, 20, 9, 11))).toBe("20-10-2026, 09:11 AM");
    expect(formatDMYTime(local(2026, 10, 20, 15, 5))).toBe("20-10-2026, 03:05 PM");
  });
  it("chart labels", () => {
    expect(formatDM(local(2026, 9, 4))).toBe("04-09");
    expect(formatDMHour(local(2026, 9, 4, 16))).toBe("04-09, 04 PM");
  });
  it("missing or bad input falls back, never throws", () => {
    expect(formatDMY(null)).toBe("N/A");
    expect(formatDMY("not a date")).toBe("N/A");
    expect(formatDMYTime(undefined, "Never")).toBe("Never");
    expect(toDate("")).toBeNull();
  });
  it("an ISO string is read as the same instant", () => {
    expect(formatDMY("2026-10-20T03:41:00Z", "x")).toMatch(/^\d{2}-\d{2}-2026$/);
  });
});

import { dataAsOfText } from "@/components/DashboardHeader";
describe("data as of", () => {
  it("says when the last successful Run Pipeline finished, or that there was none", () => {
    expect(dataAsOfText(new Date(2026, 9, 20, 9, 11).toISOString())).toBe("Data as of 20-10-2026, 09:11 AM (last Run Pipeline)");
    expect(dataAsOfText(null)).toBe("No successful Run Pipeline yet");
  });
});
