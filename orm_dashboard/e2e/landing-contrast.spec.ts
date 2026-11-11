import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";

// The public landing page must have no colour-contrast failures (WCAG AA, 4.5:1 for normal text) in either theme.
// Writes the full result next to the QA report so before/after can be compared.
const OUT = path.resolve(__dirname, "../../reports/qa-2026-11-11");

for (const theme of ["light", "dark"] as const) {
  for (const width of [1440, 390]) {
    test(`landing page colour contrast (${theme}, ${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.addInitScript(([k, v]) => { try { localStorage.setItem(k, v); } catch {} }, ["xoop-dashboard-theme", theme]);
      await page.goto("/", { waitUntil: "networkidle" });
      await page.waitForTimeout(1200);
      // scroll to the bottom in steps so every reveal-on-scroll section is shown before it is measured
      await page.evaluate(async () => {
        for (let y = 0; y < document.body.scrollHeight; y += 500) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); }
        window.scrollTo(0, 0);
      });
      await page.waitForTimeout(800);
      const res = await new AxeBuilder({ page }).exclude("nextjs-portal").withRules(["color-contrast"]).analyze();
      const rows = res.violations.flatMap((v) => v.nodes.map((n) => ({
        impact: v.impact, target: n.target.join(" "), detail: (n.any[0]?.message || "").replace(/\s+/g, " "),
      })));
      if (process.env.LANDING_AXE_LABEL) {
        fs.mkdirSync(OUT, { recursive: true });
        fs.writeFileSync(path.join(OUT, `landing-axe-${process.env.LANDING_AXE_LABEL}-${theme}-${width}.json`), JSON.stringify({ count: rows.length, rows }, null, 1));
      }
      expect(rows.filter((r) => r.impact === "serious" || r.impact === "critical"), "serious contrast failures").toEqual([]);
    });
  }
}
