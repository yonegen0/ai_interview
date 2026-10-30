/** @file production-export.test.ts @description Reject leaked mock/private assets from the static export. */
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, expect, it } from "vitest";

const script = resolve(process.cwd(), "scripts/verify-production-export.mjs");
const roots: string[] = [];

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "ai-interview-export-"));
  roots.push(root);
  mkdirSync(join(root, "_next/static"), { recursive: true });
  writeFileSync(join(root, "index.html"), "index");
  writeFileSync(join(root, "404.html"), "not found");
  writeFileSync(join(root, "_next/static/app.js"), "app");
  return root;
}

function check(root: string, env: Record<string, string> = {}) {
  return spawnSync(process.execPath, [script, root], {
    encoding: "utf8",
    env: {
      ...process.env,
      NEXT_PUBLIC_MSW_ENABLED: "false",
      POCKET_MOCK_BUILD: "false",
      ...env,
    },
  });
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

it("accepts a clean static export", () => {
  expect(check(fixture()).status).toBe(0);
});

it.each([
  "mockServiceWorker.js",
  ".env.production",
  ".npmrc",
  "private/.netrc",
  "private/.pypirc",
  "private/id_ed25519",
  "private/id_rsa",
  "_next/static/app.js.map",
  "build/private.pem",
  "terraform.tfstate",
  "test-results/output.json",
])("rejects a leaked asset: %s", (name) => {
  const root = fixture();
  const target = join(root, name);
  mkdirSync(resolve(target, ".."), { recursive: true });
  writeFileSync(target, "test");
  const result = check(root);
  expect(result.status).not.toBe(0);
  expect(result.stderr).toContain(name.startsWith("test-results/") ? "test-results" : name);
});

it("rejects a mock-enabled build regardless of its file list", () => {
  expect(check(fixture(), { NEXT_PUBLIC_MSW_ENABLED: "true" }).status).not.toBe(0);
});

it("rejects an incomplete export", () => {
  const root = fixture();
  rmSync(join(root, "404.html"));
  expect(check(root).status).not.toBe(0);
});
