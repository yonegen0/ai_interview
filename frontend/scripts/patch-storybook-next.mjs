/** @file patch-storybook-next.mjs @description Backport the upstream Next16.4 router mock fix. */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
const packageLoader = createRequire(import.meta.url);

// Exact upstream fix, without changing Storybook/Vitest peer versions:
// storybookjs/storybook v10.6.3 code/frameworks/nextjs-vite/src/routing/app-router-provider.tsx
const before = "parentCacheNode: newLazyCacheNode,";
const after = `${before}\n          parentRenderTree: { data: { bfcacheId: 0 } },`;

export function patchChunks(directory) {
  const candidates = fs
    .readdirSync(directory)
    .filter((name) => name.endsWith(".js"))
    .map((name) => ({
      file: path.join(directory, name),
      source: fs.readFileSync(path.join(directory, name), "utf8"),
    }))
    .filter(({ source }) => source.includes(before));
  if (candidates.length !== 1)
    throw new Error("Unsupported Storybook router mock layout");
  const { file, source } = candidates[0];
  if (source.includes("parentRenderTree:")) return 0;
  if (source.split(before).length !== 2)
    throw new Error("Ambiguous Storybook router mock");
  fs.writeFileSync(file, source.replace(before, after));
  return 1;
}

function main() {
  let entry;
  try {
    entry = packageLoader.resolve("@storybook/nextjs-vite");
  } catch (error) {
    if (error.code === "MODULE_NOT_FOUND") return; // Production installs can omit dev tools.
    throw error;
  }
  if (
    !JSON.parse(
      fs.readFileSync(packageLoader.resolve("next/package.json"), "utf8"),
    ).version.startsWith("16.4.")
  )
    return;
  const changed = patchChunks(
    path.join(path.dirname(entry), "_browser-chunks"),
  );
  console.log(
    `Storybook Next16.4 upstream router compatibility: ${changed ? "patched" : "present"}`,
  );
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
)
  main();
