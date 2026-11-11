import { describe, it, expect } from "vitest";
import { pickDefaultClientId } from "./defaultClient";

const list = [
  { id: "adani", name: "Adani Group", last_successful_run_at: "2026-10-01T10:00:00Z" },
  { id: "ease", name: "EaseMyTrip", last_successful_run_at: null },
  { id: "godrej", name: "Godrej Properties", last_successful_run_at: "2026-11-09T12:00:00Z" },
];

describe("pickDefaultClientId", () => {
  it("opens on the client with the most recent successful run, not the alphabetical first", () => {
    expect(pickDefaultClientId(list, null, null)).toBe("godrej");
  });
  it("the open client wins, then the remembered one, when they still exist", () => {
    expect(pickDefaultClientId(list, "ease", "godrej")).toBe("ease");
    expect(pickDefaultClientId(list, null, "adani")).toBe("adani");
  });
  it("a remembered client that is no longer listed is ignored", () => {
    expect(pickDefaultClientId(list, "gone", "gone-too")).toBe("godrej");
  });
  it("with no run information at all, falls back to the first in the list", () => {
    expect(pickDefaultClientId(list.map(c => ({ id: c.id })), null, null)).toBe("adani");
  });
  it("empty list gives null", () => {
    expect(pickDefaultClientId([], null, null)).toBeNull();
  });
});
