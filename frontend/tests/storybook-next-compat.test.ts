// @vitest-environment node
/** @file storybook-next-compat.test.ts @description Verify the narrow upstream router backport. */
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, expect, it } from "vitest";

import { patchChunks } from "../scripts/patch-storybook-next.mjs";
const directories: string[] = [];
afterEach(() => {
  for (const directory of directories.splice(0)) {
    const resolved = path.resolve(directory);
    if (
      path.dirname(resolved) !== path.resolve(tmpdir()) ||
      !path.basename(resolved).startsWith("storybook-next-")
    ) {
      throw new Error("Unexpected test cleanup path");
    }
    rmSync(resolved, { recursive: true });
  }
});

it("adds the Next16.4 cache context once while preserving the existing mock", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "storybook-next-"));
  directories.push(directory);
  const target = path.join(directory, "router.js");
  writeFileSync(
    target,
    "value: { parentCacheNode: newLazyCacheNode, url: pathname }",
  );
  expect(patchChunks(directory)).toBe(1);
  const patched = readFileSync(target, "utf8");
  expect(patched).toContain("parentRenderTree: { data: { bfcacheId: 0 } }");
  expect(patched).toContain("parentCacheNode: newLazyCacheNode");
  expect(patchChunks(directory)).toBe(0);
  expect(readFileSync(target, "utf8")).toBe(patched);
});

it("rejects an unknown upstream shape without changing files", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "storybook-next-"));
  directories.push(directory);
  const target = path.join(directory, "router.js");
  writeFileSync(target, "unrecognized vendor layout");
  expect(() => patchChunks(directory)).toThrow(
    "Unsupported Storybook router mock layout",
  );
  expect(readFileSync(target, "utf8")).toBe("unrecognized vendor layout");
});
