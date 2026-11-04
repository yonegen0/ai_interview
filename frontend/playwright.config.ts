/** @file playwright.config.ts @description Mock静的成果物でのE2E */
import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  timeout: 45000,
  // CI 全体の停止上限。個別テストが終了しない場合もレポートを残す。
  globalTimeout: process.env.CI ? 15 * 60 * 1000 : undefined,
  expect: { timeout: 12000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: {
    command: "node scripts/serve.mjs out-mock",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
  },
});
