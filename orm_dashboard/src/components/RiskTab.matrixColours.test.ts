// The risk matrix's busiest cells used "bg-red-750" / "hover:bg-red-650", which are not Tailwind colours: the cell got no
// background and its red-100 text was unreadable in light mode (seen live on 11-11-2026: "6 articles", "7 articles").
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const src = readFileSync(join(__dirname, "RiskTab.tsx"), "utf8");
const VALID_SHADES = new Set(["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"]);

describe("risk matrix cell colours", () => {
  it("uses only red shades that Tailwind defines for backgrounds and text", () => {
    const used = Array.from(src.matchAll(/(?:bg|text)-red-(\d{2,3})/g)).map((m) => m[1]);
    expect(used.length).toBeGreaterThan(0);
    expect(used.filter((s) => !VALID_SHADES.has(s))).toEqual([]);
  });

  it("gives the busiest cell a light-mode style with dark text on a red background", () => {
    expect(src).toContain('"bg-red-200 border-red-400 text-red-900');
  });
});
