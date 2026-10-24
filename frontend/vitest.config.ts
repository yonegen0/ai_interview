/** @file vitest.config.ts @description Logic/IntegrationとStorybook Browserの分離 */
import path from "node:path";
import { realpathSync } from "node:fs";
import { defineConfig } from "vitest/config";
import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import { playwright } from "@vitest/browser-playwright";
export default defineConfig({
  server: {
    host: "127.0.0.1",
    fs: {
      allow: [
        path.resolve("."),
        realpathSync("node_modules"),
        path.resolve("../contracts"),
      ],
    },
  },
  resolve: { alias: { "@": path.resolve("src") } },
  optimizeDeps: {
    include: ["@hookform/resolvers/zod", "@mui/material/Typography"],
  },
  test: {
    // Vitest 5 serves browser tests through the shared top-level API server.
    api: { host: "127.0.0.1", port: 4174, strictPort: true },
    projects: [
      {
        extends: true,
        test: {
          name: "unit",
          environment: "jsdom",
          include: ["tests/**/*.test.{ts,tsx}"],
          // Reviewer reproductions assert old bugs; keep these temporary files outside the formal suite.
          exclude: ["tests/**/*.tmp.test.{ts,tsx}"],
          setupFiles: ["./tests/setup.ts"],
        },
      },
      {
        extends: true,
        plugins: [storybookTest({ configDir: path.resolve(".storybook") })],
        test: {
          name: "storybook",
          // Stories share auth, MSW and sessionStorage fixtures inside the browser.
          fileParallelism: false,
          browser: {
            enabled: true,
            headless: true,
            provider: playwright({}),
            instances: [{ browser: "chromium" }],
          },
        },
      },
    ],
  },
});
