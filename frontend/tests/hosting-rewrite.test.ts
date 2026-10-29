/** @file hosting-rewrite.test.ts @description CloudFront Functionの静的ページ変換を実コードで回帰検証。 */
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { expect, it } from "vitest";

const rewriteSource = readFileSync(
  new URL("../../terraform/modules/frontend/rewrite.js", import.meta.url),
  "utf8",
);

function actualViewerRewrite(uri: string): string {
  const event = { request: { uri } };
  // Execute only the checked-in CloudFront Function with a synthetic event;
  // this is an offline test and makes no AWS or network request.
  runInNewContext(`${rewriteSource}\nhandler(event);`, { event }, { timeout: 1000 });
  return event.request.uri;
}

it.each([
  ["/", "/index.html"],
  ["/practice", "/practice/index.html"],
  ["/practice/", "/practice/index.html"],
  ["/login/", "/login/index.html"],
  ["/admin/questions/", "/admin/questions/index.html"],
  ["/result", "/result/index.html"],
  ["/404.html", "/404.html"],
  ["/_next/static/chunks/main.js", "/_next/static/chunks/main.js"],
  ["/images/mascot/mascot-thinking.webp", "/images/mascot/mascot-thinking.webp"],
])("rewrites CloudFront viewer URI %s to %s", (uri, expected) => {
  expect(actualViewerRewrite(uri)).toBe(expected);
});
