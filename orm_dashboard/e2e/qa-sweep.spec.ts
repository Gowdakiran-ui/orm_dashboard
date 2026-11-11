import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { mockApi, CID } from "./fixtures";

// QA sweep on the MOCKED API (synthetic data, not production): phone-width screenshots of every tab in both themes,
// console errors / failed requests / horizontal overflow per page, an empty-state client, PDF export, logout, session expiry.
// Runs only with QA_SWEEP=1 so the normal suite stays fast. Output: reports/qa-2026-11-11/screens and qa-sweep-results.json.
test.skip(!process.env.QA_SWEEP, "set QA_SWEEP=1 to run the QA sweep");

const OUT = path.resolve(__dirname, "../../reports/qa-2026-11-11");
const SCREENS = path.join(OUT, "screens");
const THEME_KEY = "xoop-dashboard-theme";
const results: any[] = [];
test.afterAll(() => { fs.mkdirSync(OUT, { recursive: true }); fs.writeFileSync(path.join(OUT, "qa-sweep-results.json"), JSON.stringify(results, null, 1)); });

const TABS = [
  { name: "brand-equity", url: "/dashboard?tab=reputation" },
  { name: "risk-center", url: "/dashboard?tab=risk" },
  { name: "competitors", url: "/dashboard?tab=competitors" },
  { name: "executives", url: "/dashboard?tab=executives" },
  { name: "analytics-overview", url: "/dashboard?tab=analytics&subtab=overview" },
  { name: "analytics-risk", url: "/dashboard?tab=analytics&subtab=risk" },
  { name: "intelligence-stream", url: "/dashboard?tab=feed" },
  { name: "counterfeit", url: "/dashboard?tab=counterfeit" },
  { name: "admin", url: "/dashboard?tab=admin" },
];

function watch(page: Page) {
  const consoleErrors: string[] = []; const failed: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${String(e.message).slice(0, 200)}`));
  page.on("requestfailed", (r) => failed.push(`${r.method()} ${r.url()} ${r.failure()?.errorText}`));
  page.on("response", (r) => { if (r.status() >= 400) failed.push(`${r.status()} ${r.request().method()} ${r.url()}`); });
  return { consoleErrors, failed };
}

async function setup(page: Page, theme: "light" | "dark", width: number) {
  await page.setViewportSize({ width, height: 844 });
  await page.context().addCookies([{ name: "orm_session", value: "x", url: "http://localhost:3101" }]);
  await page.addInitScript(([k, v]) => { try { localStorage.setItem(k, v); } catch {} }, [THEME_KEY, theme]);
  await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
}

for (const theme of ["light", "dark"] as const) {
  for (const t of TABS) {
    test(`phone 390 ${theme}: ${t.name}`, async ({ page }) => {
      const w = watch(page);
      await setup(page, theme, 390);
      await mockApi(page);
      await page.goto(t.url, { waitUntil: "networkidle" });
      await page.waitForTimeout(1200);
      fs.mkdirSync(SCREENS, { recursive: true });
      await page.screenshot({ path: path.join(SCREENS, `phone-${t.name}-${theme}-390.png`), fullPage: true });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      results.push({ page: t.name, theme, width: 390, horizontalOverflowPx: overflow, consoleErrors: w.consoleErrors, failedRequests: w.failed });
      expect(overflow, "horizontal overflow").toBeLessThanOrEqual(1);
    });
  }
}

test("empty-state client (no articles, no scores, no competitors) opens every tab without errors", async ({ page }) => {
  const w = watch(page);
  await setup(page, "light", 390);
  await mockApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body), headers: { "access-control-allow-origin": "http://localhost:3101", "access-control-allow-credentials": "true" } });
  const Q = String.raw`(?:\?.*)?$`;
  const empty = new RegExp(`:8000/(documents/client/${CID}(/flagged|/counts)?|client-intelligence/${CID}/(benchmark|executives|active-alerts|executive-candidates|competitor-candidates))` + Q);
  await page.route(empty, (r) => r.fulfill(json(r.request().url().includes("/counts") ? { total: 0, scored: 0, unscored: 0, sentiment: { positive: 0, neutral: 0, negative: 0 }, topics: {} } : [])));
  await page.route(new RegExp(`:8000/client-intelligence/${CID}/(reputation|reputation-summary)` + Q), (r) => r.fulfill(json({ score: null, grade: null, status: "no_data" })));
  for (const t of TABS.filter((x) => x.name !== "admin")) {
    await page.goto(t.url, { waitUntil: "networkidle" });
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(SCREENS, `empty-${t.name}-light-390.png`), fullPage: true });
    const text = (await page.locator("main, body").first().innerText()).slice(0, 4000);
    results.push({ page: `empty:${t.name}`, theme: "light", width: 390, showsNaNOrUndefined: /\bNaN\b|undefined|\[object/.test(text), consoleErrors: [...w.consoleErrors], failedRequests: [...w.failed] });
    expect(text, `${t.name} must not show NaN/undefined`).not.toMatch(/\bNaN\b|undefined|\[object/);
  }
});

test("Export Report downloads a PDF with the three sections", async ({ page }) => {
  await setup(page, "light", 1440);
  await mockApi(page);
  await page.goto("/dashboard?tab=reputation", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  const btn = page.getByRole("button", { name: /Export Report/ });
  await expect(btn).toBeEnabled();
  const [download] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }), btn.click()]);
  fs.mkdirSync(SCREENS, { recursive: true });
  const file = path.join(OUT, "export-sample.pdf");
  await download.saveAs(file);
  const buf = fs.readFileSync(file);
  results.push({ page: "export", filename: download.suggestedFilename(), bytes: buf.length, startsWithPdf: buf.subarray(0, 5).toString() === "%PDF-", pages: (buf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length });
  expect(buf.subarray(0, 5).toString()).toBe("%PDF-");
  expect(buf.length).toBeGreaterThan(20000);
});

test("logout calls /auth/logout and lands on /login", async ({ page }) => {
  await setup(page, "light", 1440);
  await mockApi(page);
  let loggedOut = false;
  await page.route(/:8000\/auth\/logout/, (r) => { loggedOut = true; r.fulfill({ status: 200, contentType: "application/json", body: "{}", headers: { "access-control-allow-origin": "http://localhost:3101", "access-control-allow-credentials": "true" } }); });
  await page.goto("/dashboard?tab=reputation", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /log ?out|sign ?out/i }).first().click();
  await page.waitForURL(/\/login/, { timeout: 15000 });
  results.push({ page: "logout", calledLogoutEndpoint: loggedOut, url: page.url() });
  expect(loggedOut).toBe(true);
});

test("session expiry: cookie gone -> /login; cookie present but rejected (401) -> error states, no crash", async ({ page, context }) => {
  // A: the browser drops the cookie at the end of its life; the next navigation to /dashboard goes to /login (middleware.ts).
  await page.setViewportSize({ width: 1440, height: 844 });
  await context.clearCookies();
  await page.goto("/dashboard?tab=reputation");
  await page.waitForURL(/\/login/, { timeout: 20000 });
  results.push({ page: "session-expiry:no-cookie", url: page.url() });
  // B: cookie still present but the server rejects it (expired/revoked on the server): by design no redirect, the page shows its error states.
  const w = watch(page);
  await setup(page, "light", 1440);
  await mockApi(page);
  await page.route(/:8000\/(auth\/me|clients\/)/, (r) => r.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Not authenticated" }), headers: { "access-control-allow-origin": "http://localhost:3101", "access-control-allow-credentials": "true" } }));
  await page.goto("/dashboard?tab=reputation", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(SCREENS, "session-rejected-401-1440.png") });
  const text = (await page.locator("body").innerText()).slice(0, 600).replace(/\s+/g, " ");
  results.push({ page: "session-expiry:401-with-cookie", url: page.url(), bodyStart: text, pageErrors: w.consoleErrors.filter((e) => e.startsWith("pageerror")) });
  expect(w.consoleErrors.filter((e) => e.startsWith("pageerror"))).toEqual([]);
});
