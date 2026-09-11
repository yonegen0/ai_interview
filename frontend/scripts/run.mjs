/** @file run.mjs @description 明示的Mockビルドと本番Worker除去 */
import { spawnSync } from "node:child_process";
import { existsSync, unlinkSync } from "node:fs";
import { resolve } from "node:path";
const mode = process.argv[2];
if (!["dev", "mock", "production"].includes(mode))
  throw new Error("Unknown build mode");
const env = { ...process.env };
if (mode !== "production") {
  env.NEXT_PUBLIC_MSW_ENABLED = "true";
  env.NEXT_PUBLIC_API_BASE_URL = "/api";
}
env.POCKET_MOCK_BUILD = mode === "mock" ? "true" : "false";
const result = spawnSync(
  process.execPath,
  ["node_modules/next/dist/bin/next", mode === "dev" ? "dev" : "build"],
  { env, stdio: "inherit" },
);
if (result.status !== 0) process.exit(result.status ?? 1);
if (mode === "production") {
  const worker = resolve("out/mockServiceWorker.js");
  if (existsSync(worker)) unlinkSync(worker);
}
