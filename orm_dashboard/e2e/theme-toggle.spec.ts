import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

const KEY = "xoop-dashboard-theme";
const URL = "/dashboard?tab=reputation";
const PAGE_BG = { light: "rgb(245, 247, 250)", dark: "rgb(15, 20, 25)" };

test.beforeEach(async ({ context, page }) => {
  await context.addCookies([{ name: "orm_session", value: "x", url: "http://localhost:3101" }]);
  await mockApi(page);
});

test("default is System: follows the OS setting", async ({ page }) => {
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto(URL, { waitUntil: "networkidle" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", scheme);
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe(scheme);
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", scheme === "dark" ? "#0F1419" : "#F5F7FA");
  }
});

test("choice persists across reload and wins over the OS setting", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.getByRole("radio", { name: "Light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(await page.evaluate((k) => localStorage.getItem(k), KEY)).toBe("light");
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("radio", { name: "Light theme" })).toHaveAttribute("aria-checked", "true");
});

test("no flash: theme and page colour are right before first paint", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.addInitScript((k) => { try { localStorage.setItem(k, "light"); } catch {} }, KEY);
  await page.addInitScript(() => {
    const seen: string[] = [];
    (window as unknown as { __seen: string[] }).__seen = seen;
    document.addEventListener("DOMContentLoaded", () => {
      seen.push(`${document.documentElement.dataset.theme}|${getComputedStyle(document.body).backgroundColor}`);
    });
    requestAnimationFrame(() => {
      seen.push(`${document.documentElement.dataset.theme}|${getComputedStyle(document.body).backgroundColor}`);
    });
  });
  await page.goto(URL, { waitUntil: "networkidle" });
  const seen = await page.evaluate(() => (window as unknown as { __seen: string[] }).__seen);
  expect(seen.length).toBeGreaterThan(0);
  for (const s of seen) expect(s).toBe(`light|${PAGE_BG.light}`);
});

test("focus ring uses the token colour in both themes", async ({ page }) => {
  for (const [theme, ring] of [["light", "rgb(29, 78, 216)"], ["dark", "rgb(94, 234, 212)"]] as const) {
    await page.addInitScript(([k, v]) => { try { localStorage.setItem(k, v); } catch {} }, [KEY, theme]);
    await page.goto(URL, { waitUntil: "networkidle" });
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    const outline = await page.evaluate(() => getComputedStyle(document.activeElement as Element).outlineColor);
    expect(outline).toBe(ring);
  }
});
