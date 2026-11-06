import { defineConfig } from "@playwright/test";

// E2E theme/contrast checks. The API is fully mocked in e2e/fixtures.ts, so
// no backend, login or database is needed. Run: npm run test:e2e
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3101", trace: "off" },
  webServer: {
    command: "npm run dev -- --port 3101",
    url: "http://localhost:3101/login",
    reuseExistingServer: true,
    timeout: 180_000,
  },
});
