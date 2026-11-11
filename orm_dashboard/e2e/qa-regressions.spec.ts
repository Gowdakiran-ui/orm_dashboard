import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { mockApi, CID } from "./fixtures";

// Regressions found on the live site on 11-11-2026 that the shared fixtures did not reach:
//  1. a risk-matrix cell with more than 5 articles had no background and near-white text in light mode;
//  2. at phone width the header's "Data as of ..." text ran off the right edge of the screen.
const OUT = path.resolve(__dirname, "../../reports/qa-2026-11-11/screens");
const THEME_KEY = "xoop-dashboard-theme";

const busyDoc = (i: number) => ({
  id: `busy-${i}`, title: `Regulator order ${i} against the company`, source: "Example RSS Source", document_type: "rss",
  timestamp: new Date(Date.UTC(2026, 9, 1 + i, 7)).toISOString(), status: "COMPLETED", sentiment: -1, risk: 62, scored: true,
  risk_level: "HIGH", risk_exact: 62, risk_sentiment: "Negative", date_basis: "published", risk_explainability: { confidence: 0.5 },
  original_content: "", extracted_entities: [], topic: "Legal Risk", reputation_impact: "+0.0", url: "https://example.com/a",
});

async function open(page: Page, theme: "light" | "dark", width: number, url: string) {
  await page.setViewportSize({ width, height: 900 });
  await page.context().addCookies([{ name: "orm_session", value: "x", url: "http://localhost:3101" }]);
  await page.addInitScript(([k, v]) => { try { localStorage.setItem(k, v); } catch {} }, [THEME_KEY, theme]);
  await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
  await mockApi(page);
  const json = (body: unknown) => ({
    status: 200, contentType: "application/json", body: JSON.stringify(body),
    headers: { "access-control-allow-origin": "http://localhost:3101", "access-control-allow-credentials": "true" },
  });
  // registered after mockApi, so these win
  await page.route(new RegExp(`:8000/documents/client/${CID}(\\?.*)?$`), (r) => r.fulfill(json(Array.from({ length: 9 }, (_, i) => busyDoc(i)))));
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  fs.mkdirSync(OUT, { recursive: true });
}

for (const theme of ["light", "dark"] as const) {
  test(`risk matrix: a cell with more than 5 articles is readable (${theme})`, async ({ page }) => {
    await open(page, theme, 1440, "/dashboard?tab=risk");
    const cell = page.getByText("9 articles", { exact: true }).first();
    await expect(cell).toBeVisible();
    const bg = await cell.evaluate((el) => getComputedStyle(el.parentElement as HTMLElement).backgroundColor);
    expect(bg, "the busiest cell must have a background colour").not.toBe("rgba(0, 0, 0, 0)");
    await cell.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(OUT, `fix-risk-matrix-busy-cell-${theme}-1440.png`) });
    const res = await new AxeBuilder({ page }).exclude("nextjs-portal").withRules(["color-contrast"]).analyze();
    const serious = res.violations.filter((v) => v.impact === "serious" || v.impact === "critical").flatMap((v) => v.nodes.map((n) => n.target.join(" ")));
    expect(serious).toEqual([]);
  });
}

test("phone width: the header stays inside the screen and still shows 'Data as of'", async ({ page }) => {
  await open(page, "light", 390, "/dashboard?tab=risk");
  const header = page.locator("header").first();
  await expect(header.getByTestId("data-as-of-mobile")).toBeVisible();
  await expect(header.getByTestId("data-as-of-mobile")).toContainText("Data as of 05-11-2026");
  const overflowing = await header.evaluate((h) => {
    const vw = window.innerWidth;
    return Array.from(h.querySelectorAll("*")).filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && r.right > vw + 1;
    }).map((el) => `${el.tagName}.${String(el.className).slice(0, 40)}`);
  });
  expect(overflowing).toEqual([]);
  await page.screenshot({ path: path.join(OUT, "fix-header-390-light.png") });
});

test("desktop width: 'Data as of' is shown once, on the right", async ({ page }) => {
  await open(page, "light", 1440, "/dashboard?tab=risk");
  const header = page.locator("header").first();
  await expect(header.getByTestId("data-as-of-mobile")).toBeHidden();
  await expect(header.getByText(/Data as of 05-11-2026/).last()).toBeVisible();
});