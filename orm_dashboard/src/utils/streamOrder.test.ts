import { describe, it, expect } from "vitest";
import { orderStream, flaggedLeadCount, byRiskThenDate } from "./streamOrder";

const doc = (id: string, ts: string, risk = 0, extra: any = {}) => ({ id, timestamp: ts, risk, risk_exact: risk, ...extra });

describe("orderStream", () => {
  const recent = [doc("n1", "2026-11-09T10:00:00Z"), doc("n2", "2026-11-08T10:00:00Z"), doc("n3", "2026-11-07T10:00:00Z")];

  it("puts flagged articles of any age above the newest list, strongest first, then newest", () => {
    const flagged = [doc("f-old-high", "2025-01-01T00:00:00Z", 51), doc("f-crit", "2024-06-01T00:00:00Z", 79), doc("f-new-high", "2026-09-01T00:00:00Z", 51)];
    expect(orderStream(recent, flagged).map(d => d.id)).toEqual(["f-crit", "f-new-high", "f-old-high", "n1", "n2", "n3"]);
  });

  it("does not repeat an article that is in both lists, and keeps the newest-first order of the rest", () => {
    const flagged = [doc("n2", "2026-11-08T10:00:00Z", 60), doc("f1", "2026-01-01T00:00:00Z", 40)];
    const out = orderStream(recent, flagged).map(d => d.id);
    expect(out).toEqual(["n2", "f1", "n1", "n3"]);
    expect(new Set(out).size).toBe(out.length);
  });

  it("is the plain list when no flagged list came back (failed fetch, none flagged, missing)", () => {
    expect(orderStream(recent, [])).toBe(recent);
    expect(orderStream(recent, undefined)).toBe(recent);
    expect(orderStream(recent, null)).toBe(recent);
    expect(orderStream(null, undefined)).toEqual([]);
    expect(orderStream(undefined, [doc("f", "2026-01-01T00:00:00Z", 55)]).map(d => d.id)).toEqual(["f"]);
  });

  it("ignores malformed rows and never changes its inputs", () => {
    const flagged = [null, { title: "no id" }, doc("f", "2026-01-01T00:00:00Z", 55)] as any[];
    const before = JSON.stringify([recent, flagged]);
    expect(orderStream([...recent, null as any], flagged).slice(0, 4).map(d => d.id)).toEqual(["f", "n1", "n2", "n3"]);
    expect(JSON.stringify([recent, flagged])).toBe(before);
  });

  it("breaks exact ties by date then id so the order is stable between refreshes", () => {
    const a = doc("a", "2026-05-01T00:00:00Z", 51), b = doc("b", "2026-05-01T00:00:00Z", 51), c = doc("c", "2026-06-01T00:00:00Z", 51);
    expect([a, b, c].sort(byRiskThenDate).map(d => d.id)).toEqual(["c", "a", "b"]);
    expect([c, b, a].sort(byRiskThenDate).map(d => d.id)).toEqual(["c", "a", "b"]);
  });

  it("uses the unrounded score when the row has one", () => {
    const x = { id: "x", timestamp: "2026-01-01T00:00:00Z", risk: 51, risk_exact: 51.0 };
    const y = { id: "y", timestamp: "2026-01-01T00:00:00Z", risk: 51, risk_exact: 74.7 };
    expect([x, y].sort(byRiskThenDate).map(d => d.id)).toEqual(["y", "x"]);
  });
});

describe("flaggedLeadCount", () => {
  it("counts the articles that lead because they are flagged", () => {
    const flagged = [doc("f1", "2026-01-01T00:00:00Z", 55), doc("f2", "2026-01-02T00:00:00Z", 45)];
    const ordered = orderStream([doc("n1", "2026-11-09T00:00:00Z")], flagged);
    expect(flaggedLeadCount(ordered, flagged)).toBe(2);
    expect(flaggedLeadCount(ordered, [])).toBe(0);
    expect(flaggedLeadCount(ordered, undefined)).toBe(0);
  });
});
