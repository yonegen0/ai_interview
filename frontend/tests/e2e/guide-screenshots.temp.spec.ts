/** @file guide-screenshots.temp.spec.ts @description Temporary Mock E2E asset capture for guide visuals; removed after asset commit. */
import { test, expect, type Page } from "@playwright/test";

async function capture(page: Page, name: string) {
  const data = (await page.screenshot({
    type: "jpeg",
    quality: 48,
    animations: "disabled",
    caret: "hide",
  })).toString("base64");
  console.log("GUIDE_IMAGE_" + name + "_BEGIN");
  for (let start = 0; start < data.length; start += 4000) {
    console.log("GUIDE64=" + data.slice(start, start + 4000));
  }
  console.log("GUIDE_IMAGE_" + name + "_END");
}

test("capture actual Mock app screens for basic guide", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const choose = page.getByRole("link", { name: /カテゴリから選ぶ/ });
  await expect(choose).toBeVisible();
  await choose.scrollIntoViewIfNeeded();
  await capture(page, "start");

  await page.goto("/practice/");
  await page.getByRole("button", { name: "カテゴリ練習", exact: true }).click();
  await page.getByRole("combobox", { name: "練習するカテゴリ" }).click();
  await page.getByRole("option", { name: /^転職理由（\d+問）$/ }).click();
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  const answer = page.getByLabel("あなたの回答");
  await expect(answer).toBeVisible();
  await answer.scrollIntoViewIfNeeded();
  await capture(page, "answer");
  await answer.fill("これまでの経験を通して課題を整理し、改善を重ねてきました。今後もその経験を活かしたいと考えています。");
  await page.getByRole("button", { name: "回答を送信", exact: true }).click();
  await expect(page.getByRole("heading", { name: "今回のフィードバック" })).toBeVisible();
  await page.getByRole("heading", { name: "総合評価" }).scrollIntoViewIfNeeded();
  await capture(page, "feedback");

  await page.goto("/");
  await expect(page.getByText("面接練習の進捗")).toBeVisible();
  await page.getByText("面接練習の進捗").scrollIntoViewIfNeeded();
  await capture(page, "progress");
});