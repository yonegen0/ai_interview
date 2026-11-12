/** @file star-assist-tutorial.spec.ts @description 実練習の回答を守る12ステップ疑似体験E2E。 */
import { expect, test, type Page } from "@playwright/test";
import {
  TUTORIAL_CANDIDATES, TUTORIAL_EDITED_A, TUTORIAL_NOTES,
  TUTORIAL_QUESTION, TUTORIAL_CANDIDATE_DESCRIPTIONS,
  TUTORIAL_EDIT_BEFORE, TUTORIAL_EDIT_AFTER,
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

for (const [width, height] of [[375, 667], [390, 844], [430, 932], [1440, 900]]) {
  test("STAR tutorial " + width + "px: only Next, reversibility, no API writes, real answer preserved", async ({
    page,
  }) => {
    await page.setViewportSize({ width, height });
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
    const dialog = page.getByRole("dialog", { name: "エピソード作成アシストの使い方を体験" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "体験用の質問" })).toBeVisible();
    await expect(dialog.getByText(TUTORIAL_QUESTION)).toBeVisible();
    await expect(dialog.getByText("実際の回答・下書きには保存されません。")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
    const next = dialog.getByRole("button", { name: "次へ" });
    const back = dialog.getByRole("button", { name: "戻る", exact: true });
    await expect(back).toBeDisabled();
    await next.click();
    await expect(dialog.getByRole("textbox", { name: "S 状況" })).toHaveValue(TUTORIAL_NOTES.S);
    await expect(dialog.getByRole("textbox", { name: "S 状況" })).toBeInViewport();
    await next.click();
    await expect(dialog.getByRole("textbox", { name: "T 課題" })).toHaveValue(TUTORIAL_NOTES.T);
    await expect(dialog.getByRole("textbox", { name: "T 課題" })).toBeInViewport();
    await next.click();
    await expect(dialog.getByRole("textbox", { name: "A 本人の行動" })).toHaveValue(TUTORIAL_NOTES.A);
    await expect(dialog.getByRole("textbox", { name: "A 本人の行動" })).toBeInViewport();
    await next.click();
    await expect(dialog.getByRole("textbox", { name: "R 結果・学び" })).toHaveValue(TUTORIAL_NOTES.R);
    await expect(dialog.getByRole("textbox", { name: "R 結果・学び" })).toBeInViewport();
    await expect(dialog.getByRole("textbox", { name: "R 結果・学び" })).toHaveAttribute("readonly");
    await expect(dialog.getByLabel("結果・学びの記入例")).toBeVisible();
    await expect(dialog.getByRole("textbox")).toHaveCount(1);
    await back.click();
    await expect(dialog.getByRole("textbox", { name: "A 本人の行動" })).toHaveValue(TUTORIAL_NOTES.A);
    await next.click();
    await next.click();
    await expect(dialog.getByText("接客・販売・サービス", { exact: true })).toBeVisible();
    await expect(dialog.getByRole("textbox")).toHaveCount(3);
    await expect(dialog.getByRole("button", { name: "このカテゴリを14日保存" })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "3案を生成（1回）" })).toBeDisabled();
    await expect(dialog.getByText("本番の生成ボタンの見本です。体験では「次へ」を押してください。")).toBeVisible();
    await expect(dialog.getByText("STEP 6 / 12")).toBeVisible();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[0].text)).toBeVisible();
    await expect(dialog.getByText(TUTORIAL_CANDIDATE_DESCRIPTIONS.A)).toBeVisible();
    await expect(dialog.getByText("B 行動重視")).toBeVisible();
    await expect(dialog.getByRole("tab", { name: "B 行動重視" })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "この回答を使う" })).toBeDisabled();
    await expect(dialog.getByText(/表示中：A案/)).toBeVisible();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[1].text)).toBeVisible();
    await expect(dialog.getByText(TUTORIAL_CANDIDATE_DESCRIPTIONS.B)).toBeVisible();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[2].text)).toBeVisible();
    await expect(dialog.getByText(TUTORIAL_CANDIDATE_DESCRIPTIONS.C)).toBeVisible();
    await back.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[1].text)).toBeVisible();
    await next.click();
    await next.click();
    await expect(dialog.getByText(TUTORIAL_CANDIDATES[0].text)).toBeVisible();
    await next.click();
    await expect(dialog.getByRole("textbox", { name: "編集画面の文章" })).toHaveValue(TUTORIAL_CANDIDATES[0].text);
    await expect(dialog.getByText(/修正する箇所は最後の一文/)).toBeVisible();
    await expect(dialog.getByLabel("修正前後の比較")).toHaveCount(0);
    await next.click();
    const comparison = dialog.getByLabel("修正前後の比較");
    await expect(comparison).toBeInViewport();
    await expect(comparison.getByLabel("修正前")).toContainText(TUTORIAL_EDIT_BEFORE);
    await expect(comparison.getByLabel("修正後")).toContainText(TUTORIAL_EDIT_AFTER);
    await expect(comparison.getByText("抽象的な表現を、学んだことが伝わる具体的な言葉に整えました。")).toBeVisible();
    await expect(dialog.getByRole("textbox", { name: "編集画面の文章" })).toHaveValue(TUTORIAL_EDITED_A);
    await expect(dialog.getByRole("textbox", { name: "編集画面の文章" })).toHaveAttribute("readonly");
    await expect(dialog.getByRole("textbox", { name: "編集画面の文章" })).toHaveCount(1);
    await expect(dialog.getByText("274 / 600文字")).toBeVisible();
    expect(await comparison.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await back.click();
    await expect(dialog.getByLabel("修正前後の比較")).toHaveCount(0);
    await expect(dialog.getByRole("textbox", { name: "編集画面の文章" })).toHaveValue(TUTORIAL_CANDIDATES[0].text);
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


for (const width of [375, 1440]) {
  test("tutorial shares STAR input card styles with production at " + width + "px", async ({ page }) => {
    await page.setViewportSize({ width, height: width === 375 ? 667 : 900 });
    await begin(page);
    await page.getByRole("button", { name: /エピソード作成アシスト/ }).click();
    const production = page.getByRole("dialog", { name: /エピソード作成アシスト/ });
    await expect(production).toBeVisible();

    // Compare common presentation properties; the tutorial dialog itself may be a different width.
    const cardStyle = async (locator: ReturnType<typeof production.getByLabel>) => locator.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        padding: style.padding, border: style.border, radius: style.borderRadius,
        display: style.display, gap: style.gap, background: style.backgroundColor,
      };
    });
    const productionCard = await cardStyle(production.getByLabel("状況の入力"));
    const productionTips = await cardStyle(production.getByLabel("状況の記入例"));
    await production.getByRole("button", { name: "エピソード作成アシストを閉じる" }).click();
    await page.getByRole("button", { name: "使い方を体験する" }).click();

    const tutorial = page.getByRole("dialog", { name: "エピソード作成アシストの使い方を体験" });
    await expect(tutorial.getByLabel("状況の入力")).toBeVisible();
    expect(await cardStyle(tutorial.getByLabel("状況の入力"))).toEqual(productionCard);
    expect(await cardStyle(tutorial.getByLabel("状況の記入例"))).toEqual(productionTips);
    await expect(tutorial.getByRole("textbox", { name: "S 状況" })).toHaveAttribute("readonly");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
      .toBe(true);
  });
}

/** One fixed lesson is reused by every assist mode; production dialogs are mode-specific. */
for (const [category, assistLabel] of [
  ["仕事経験", "エピソード作成アシスト"],
  ["自己紹介", "簡潔回答アシスト"],
  ["転職理由", "転職理由アシスト"],
  ["志望動機", "志望動機アシスト"],
  ["キャリア", "キャリアプランアシスト"],
] as const) {
  test(`completion launches production ${assistLabel} from ${category}`, async ({ page }) => {
    await page.goto("/practice/");
    await page.getByRole("button", { name: "カテゴリ練習", exact: true }).click();
    await page.getByRole("combobox", { name: "練習するカテゴリ" }).click();
    await page.getByRole("option", { name: new RegExp("^" + category + "（\\\\d+問）$") }).click();
    await page.getByRole("button", { name: "練習を始める", exact: true }).click();
    const original = "回答作成画面の本人入力は維持する。";
    await page.getByLabel("あなたの回答").fill(original);
    await page.getByRole("button", { name: "使い方を体験する" }).click();
    const tutorial = page.getByRole("dialog", { name: "エピソード作成アシストの使い方を体験" });
    for (let i = 0; i < 12; i++) {
      await tutorial.getByRole("button", { name: "次へ", exact: true }).click();
    }
    await tutorial.getByRole("button", { name: "アシスト機能を試してみる" }).click();
    await expect(tutorial).not.toBeVisible();
    await expect(page.getByRole("dialog", { name: new RegExp(assistLabel) })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(1);
    await expect(page.getByLabel("あなたの回答")).toHaveValue(original);
  });
}

test("none-assist question explains the exception and delegates category exit confirmation", async ({ page }) => {
  await page.goto("/practice/");
  await page.getByRole("button", { name: "カテゴリ練習", exact: true }).click();
  await page.getByRole("combobox", { name: "練習するカテゴリ" }).click();
  await page.getByRole("option", { name: /^逆質問（\\d+問）$/ }).click();
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  await expect(page.getByRole("button", { name: "回答アシストの使い方を体験" })).toBeVisible();
  await expect(page.getByRole("button", { name: /エピソード作成アシスト/ })).toHaveCount(0);
  await page.getByLabel("あなたの回答").fill("回答を維持する入力");
  await page.getByRole("button", { name: "回答アシストの使い方を体験" }).click();
  const tutorial = page.getByRole("dialog", { name: "エピソード作成アシストの使い方を体験" });
  for (let i = 0; i < 12; i++) {
    await tutorial.getByRole("button", { name: "次へ", exact: true }).click();
  }
  await tutorial.getByRole("button", { name: "アシスト機能を試してみる" }).click();
  await expect(tutorial).not.toBeVisible();
  const unsupported = page.getByRole("dialog", { name: "この質問では回答アシストを使用できません" });
  await expect(unsupported).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await unsupported.getByRole("button", { name: "別の質問を選ぶ" }).click();
  const confirm = page.getByRole("dialog", { name: "練習を終了しますか？" });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "続ける" }).click();
  await expect(page.getByLabel("あなたの回答")).toHaveValue("回答を維持する入力");
  await page.getByRole("button", { name: "回答アシストの使い方を体験" }).click();
  const again = page.getByRole("dialog", { name: "エピソード作成アシストの使い方を体験" });
  for (let i = 0; i < 12; i++) {
    await again.getByRole("button", { name: "次へ", exact: true }).click();
  }
  await again.getByRole("button", { name: "アシスト機能を試してみる" }).click();
  await page.getByRole("dialog", { name: "この質問では回答アシストを使用できません" })
    .getByRole("button", { name: "別の質問を選ぶ" }).click();
  await page.getByRole("dialog", { name: "練習を終了しますか？" })
    .getByRole("button", { name: "終了する" }).click();
  await expect(page).toHaveURL(/\\/practice\\/category\\//);
});
