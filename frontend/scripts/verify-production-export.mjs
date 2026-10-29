/** @file verify-production-export.mjs @description Reject private or mock assets in the production static export. */
import { existsSync, readdirSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";

const root = resolve(process.argv[2] ?? "out");
const forbiddenNames = new Set([
  "mockserviceworker.js",
  ".git",
  ".aws",
  ".next",
  "node_modules",
  "out-mock",
  "storybook-static",
  "playwright-report",
  "test-results",
  "__tests__",
]);
const forbiddenFile = /(?:^\.env(?:\.|$)|^\.ds_store$|\.(?:map|pem|key|tfstate)(?:\.|$)|^terraform\.tfvars(?:\.json)?$)/i;

if (process.env.NEXT_PUBLIC_MSW_ENABLED === "true" || process.env.POCKET_MOCK_BUILD === "true") {
  throw new Error("Refusing to verify a mock-enabled production export");
}
if (!existsSync(join(root, "index.html")) || !existsSync(join(root, "404.html")) || !existsSync(join(root, "_next", "static"))) {
  throw new Error("Production static export is incomplete");
}

const unsafe = [];
function inspect(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    const rel = relative(root, path).split(sep).join("/");
    if (forbiddenNames.has(entry.name.toLowerCase()) || forbiddenFile.test(entry.name)) {
      unsafe.push(rel);
    } else if (entry.isDirectory()) {
      inspect(path);
    } else if (entry.isSymbolicLink() || !entry.isFile()) {
      unsafe.push(rel);
    }
  }
}
inspect(root);
if (unsafe.length) throw new Error("Production export contains forbidden files: " + unsafe.slice(0, 20).join(", "));
console.log("Production export safety check passed");
