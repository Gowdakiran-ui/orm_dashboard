import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { mockApi } from "./fixtures";

// Every page/state is checked in both themes at 1440px and 390px.
// THEME_TAG=before|after selects the screenshot folder under ../reports/theme/.
// Fails on any serious/critical colour-contrast violation.
const TAG = process.env.THEME_TAG ?? "after";
const OUT = path.resolve(__dirname, "../../reports/theme", TAG);
const THEME_KEY = "xoop-dashboard-theme";
const SOFT = process.env.THEME_SOFT === "1"; // forensics mode: record, don't fail

type PageDef = { name: string; url: string; prep?: (p: Page) => Promise<void> };
const dash = (tab: string, extra = "") => `/dashboard?tab=${tab}${extra}`;
const PAGES: PageDef[] = [
  { name: "landing", url: "/" },
  { name: "login", url: "/login" },
  { name: "brand-equity", url: dash("reputation") },
  { name: "risk-center", url: dash("risk") },
  { name: "competitors", url: dash("competitors") },
  { name: "executives", url: dash("executives") },
  { name: "analytics-overview", url: dash("analytics", "&subtab=overview") },
  { name: "analytics-risk", url: dash("analytics", "&subtab=risk") },
  { name: "intelligence-stream", url: dash("feed") },
  {
    name: "stream-details-drawer",
    url: dash("feed"),
    prep: async (p) => {
      const btn = p.getByRole("button", { name: /details/i }).first();
      if (await btn.count()) {
        await btn.click();
        await p.waitForTimeout(600);
      }
    },
  },
  { name: "counterfeit", url: dash("counterfeit") },
  { name: "admin", url: dash("admin") },
];

for (const theme of ["light", "dark"] as const) {
  for (const vp of [{ w: 1440, h: 900 }, { w: 390, h: 844 }]) {
    test.describe(`${theme} ${vp.w}`, () => {
      for (const def of PAGES) {
        test(def.name, async ({ page, context }) => {
          await page.setViewportSize({ width: vp.w, height: vp.h });
          await context.addCookies([{ name: "orm_session", value: "x", url: "http://localhost:3101" }]);
          await page.addInitScript(([k, v]) => { try { localStorage.setItem(k, v); } catch {} }, [THEME_KEY, theme]);
          await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
          await mockApi(page);
          await page.goto(def.url, { waitUntil: "networkidle" });
          await page.waitForTimeout(1500);
          if (def.prep) await def.prep(page);
          fs.mkdirSync(OUT, { recursive: true });
          await page.screenshot({ path: path.join(OUT, `${def.name}-${theme}-${vp.w}.png`), fullPage: true });
          const res = await new AxeBuilder({ page }).exclude("nextjs-portal").withRules(["color-contrast"]).analyze();
          const bad = res.violations.flatMap((v) =>
            v.nodes.map((n) => ({
              impact: v.impact,
              target: n.target.join(" "),
              summary: (n.any[0]?.message ?? "").slice(0, 200),
              data: n.any[0]?.data ?? null,
            })),
          );
          fs.writeFileSync(path.join(OUT, `${def.name}-${theme}-${vp.w}.axe.json`), JSON.stringify(bad, null, 1));
          if (SOFT) return;
          const blocking = bad.filter((b) => b.impact === "serious" || b.impact === "critical");
          expect(blocking, `${def.name} ${theme} ${vp.w}: ${blocking.length} contrast violations`).toEqual([]);
        });
      }
    });
  }
}
