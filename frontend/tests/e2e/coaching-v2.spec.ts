/** @file coaching-v2.spec.ts @description Real browser V2 rounds, failed reload, historical views, and evaluation-only retry. */
import { test, expect, type Page } from "@playwright/test";
async function begin(page: Page, scenario: string) {
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/practice/");
  await page.getByRole("button", { name: "カテゴリ練習", exact: true }).click();
  await page.getByRole("button", { name: /^転職理由/ }).click();
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  await expect(page.getByLabel("あなたの回答")).toBeVisible();
  await page.evaluate(
    (value) => sessionStorage.setItem("pocket:scenario", value),
    scenario,
  );
}
async function answer(page: Page, text: string) {
  await page.getByLabel("あなたの回答").fill(text);
  await page.getByRole("button", { name: "回答を送信", exact: true }).click();
}
async function feedback(page: Page) {
  await expect(
    page.getByRole("heading", { name: "今回のフィードバック", exact: true }),
  ).toBeVisible();
}
test("three rounds retain drafts on reload, past results stay read-only, completed retry starts empty", async ({
  page,
}) => {
  await begin(page, "coaching_max");
  await answer(page, "🙂".repeat(400));
  await feedback(page);
  const first = page.url();
  for (let round = 1; round <= 3; round++) {
    await expect(
      page.getByRole("heading", { name: `深掘り質問 ${round} / 3` }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "次の質問へ", exact: true }),
    ).toHaveCount(0);
    if (round === 1) {
      await page.getByLabel("あなたの回答").fill("分からない");
      await page.reload();
      await expect(page.getByLabel("あなたの回答")).toHaveValue("分からない");
    }
    await answer(
      page,
      round === 1 ? "分からない" : `本人の行動を確認しました。${round}`,
    );
    await feedback(page);
  }
  await expect(page.getByRole("heading", { name: "改善回答" })).toBeVisible();
  await expect(page.getByLabel("あなたの回答")).toHaveCount(0);
  const completed = page.url();
  const count = await page.evaluate(() => {
    const state = JSON.parse(sessionStorage.getItem("pocket:mock:v3")!);
    return Object.values(state.coachings).map(
      (h) => (h as { coachingCount: number }).coachingCount,
    );
  });
  expect(count).toEqual([3]);
  await page.goto(first);
  await feedback(page);
  await expect(page.getByLabel("あなたの回答")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "同じ質問に再挑戦" }),
  ).toHaveCount(0);
  await page.goto(completed);
  await feedback(page);
  await page.getByRole("link", { name: "同じ質問に再挑戦" }).click();
  await expect(page.getByLabel("あなたの回答")).toHaveValue("");
  await page.evaluate(() =>
    sessionStorage.setItem("pocket:scenario", "success"),
  );
  await answer(page, "新しく練習します。");
  await feedback(page);
  await expect(page.getByText(/初回回答 9文字/)).toBeVisible();
  await expect(
    page.locator("summary").filter({ hasText: "深掘りの履歴" }),
  ).toHaveCount(0);
});
test("failed follow-up restores accepted history on reload and retries without an answer payload", async ({
  page,
}) => {
  await begin(page, "coaching");
  await answer(page, "顧客を支援したいです。");
  await feedback(page);
  await expect(
    page.getByRole("heading", { name: "深掘り質問 1 / 3" }),
  ).toBeVisible();
  await page.evaluate(() =>
    sessionStorage.setItem("pocket:scenario", "evaluation_failed"),
  );
  await answer(page, "いいえ。提案したのは上司です。");
  await expect(
    page.getByRole("heading", { name: "評価の作成に失敗しました" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("いいえ。提案したのは上司です。", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("あなたの回答")).toHaveCount(0);
  await page.evaluate(() =>
    sessionStorage.setItem("pocket:scenario", "success"),
  );
  await page.getByRole("button", { name: "同じ回答で評価を再試行" }).click();
  await feedback(page);
  await expect(page.getByText("深掘りの履歴（1回）")).toBeVisible();
  const operations = await page.evaluate(() => {
    const state = JSON.parse(sessionStorage.getItem("pocket:mock:v3")!);
    return Object.values(state.requests)
      .map((r) =>
        JSON.parse(
          (r as { fingerprint: string }).fingerprint
            .split(":")
            .slice(1)
            .join(":"),
        ),
      )
      .filter((body) => body.kind);
  });
  expect(operations.at(-1)).toMatchObject({ kind: "retry_evaluation" });
  expect(operations.at(-1)).not.toHaveProperty("answer");
  expect(operations.at(-1)).not.toHaveProperty("questionId");
});
