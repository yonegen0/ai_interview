/** @file star-assist-tutorial.spec.ts @description 実練習の回答を守る12ステップ疑似体験E2E。 */
import { expect, test, type Page } from "@playwright/test";
import {
  TUTORIAL_CANDIDATES, TUTORIAL_EDITED_A, TUTORIAL_NOTES,
} from "../../src/features/starAssist/tutorial/tutorialData";

async function begin(page: Page) {
  await page.goto("/practice/");
  await page.getByRole("button", { name: "カテゴリ練習", exact: true }).click();
  await page.getByRole("combobox", { name: "練習するカテゴリ" }).click();
  await page.getByRole("option", { name: /^仕事経験（\d+問）$/ }).click();
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  await expect(page.getByLabel("あなたの回答")).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "下書き：" }))
    .toContainText("保存済");
}

for (const width of [390, 1440]) {
  test("STAR tutorial " + width + "px: only Next, reversibility, no API writes, real answer preserved", async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await begin(page);
    const realAnswer = "本人が入力していた回答です。体験によって上書きされません。";
    await page.getByLabel("あなたの回答").fill(realAnswer);
    await expect(page.getByRole("status").filter({ hasText: "下書き：" }))
      .toContainText("保存済");
    // Complete regular debounce before observing operations caused by the tutorial.
    await page.waitForTimeout(1100);
    const writes: string[] = [];
    page.on("request", (request) => {
      if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method()))
        writes.push(request.method() + " " + request.url());
    });
    const launch = page.getByRole("button", { name: "使い方を体験する" });
    await expect(launch).toBeVisible();
    await launch.click();
    const dialog = page.getByRole("dialog", { name: "STARアシストの使い方を体験" });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
    const next = dialog.getByRole("button", { name: "次へ" });
    const back = dialog.getByRole("button", { name: "戻る" });
    await expect(back).toBeDisabled();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_NOTES.S)).toBeVisible();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_NOTES.T)).toBeVisible();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_NOTES.A)).toBeVisible();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_NOTES.R)).toBeVisible();
    await back.click();
    await expect(dialog.getByText("未入力", { exact: true })).toHaveCount(1);
    await next.click();
    await next.click();
    await expect(dialog.getByText("応募先カテゴリ：事務・受付")).toBeVisible();
    await dialog.getByText("3案を生成（1回）").click();
    await expect(dialog.getByText("STEP 6 / 12")).toBeVisible();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[0].text)).toBeVisible();
    await dialog.getByText("B 行動重視").click();
    await expect(dialog.getByText(/表示中：A案/)).toBeVisible();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[1].text)).toBeVisible();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[2].text)).toBeVisible();
    await back.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[1].text)).toBeVisible();
    await next.click();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[0].text)).toBeVisible();
    await next.click();
    await expect(dialog.getByLabel("編集画面の文章")).toContainText(TUTORIAL_CANDIDATES[0].text);
    await next.click();
    await expect(dialog.getByLabel("編集画面の文章")).toContainText(TUTORIAL_EDITED_A);
    await back.click();
    await expect(dialog.getByLabel("編集画面の文章")).toContainText(TUTORIAL_CANDIDATES[0].text);
    await next.click();
    await next.click();
    await expect(dialog.getByLabel("体験用回答欄")).toContainText(TUTORIAL_EDITED_A);
    await expect(dialog.getByRole("heading", { name: "チュートリアル完了！" })).toBeVisible();
    await expect(dialog.getByRole("textbox")).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "もう一度体験する" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
      .toBe(true);
    await dialog.getByRole("button", { name: "もう一度体験する" }).click();
    await expect(dialog.getByText("STEP 1 / 12")).toBeVisible();
    await dialog.getByRole("button", { name: "終了" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(launch).toBeFocused();
    await expect(page.getByLabel("あなたの回答")).toHaveValue(realAnswer);
    expect(writes).toEqual([]);
    // Normal assistance is still available after closing the tutorial.
    await page.getByRole("button", { name: /エピソード作成アシスト/ }).click();
    await expect(page.getByRole("dialog", { name: /エピソード作成アシスト/ }))
      .toBeVisible();
  });
}
