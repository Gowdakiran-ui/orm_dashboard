// Guard for the public landing page copy: wording the feature inventory (reports/xoop-feature-inventory-2026-11-05.md, section 8) lists as NOT BUILT
// must not come back. XOOP has no behaviour, search or stakeholder signals; it collects news, social and video coverage and scores the people named in it.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const src = readFileSync(join(__dirname, "page.tsx"), "utf-8");

describe("landing page copy", () => {
  it("does not mention stakeholder, behaviour or search signals", () => {
    expect(src).not.toMatch(/stakeholder/i);
    expect(src).not.toMatch(/behaviou?r,? search/i);
    expect(src).not.toMatch(/search\s+and\s+stakeholder/i);
    expect(src).not.toMatch(/connects conversations/i);
  });

  it("describes what is built: news, social and video coverage", () => {
    expect(src).toContain("XOOP brings news, social and video");
    expect(src).toContain("We name the executive or the specific story actually carrying the coverage.");
  });
});
