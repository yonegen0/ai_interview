/** @file question-management.spec.ts @description 管理者編集から新規練習への反映・完了・旧質問保持。 */
import { test, expect } from "@playwright/test";
test("ADMIN login edits, publishes, adds/removes/reorders, and keeps an existing practice snapshot", async ({
  page,
}) => {
  await page.goto("/login/?returnTo=%2Fadmin%2Fquestions%2F");
  await page
    .getByLabel("メールアドレス", { exact: true })
    .fill("admin@example.invalid");
  await page
    .getByRole("button", { name: "確認コードを送る", exact: true })
    .click();
  await page.getByLabel("確認コード", { exact: true }).fill("123456");
  await page.getByRole("button", { name: "ログインする", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "質問管理", exact: true }),
  ).toBeVisible();
  await page.goto("/practice/");
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "自己紹介をお願いしてもよろしいでしょうか？",
    }),
  ).toBeVisible();
  const oldPractice = page.url();
  await page.getByRole("link", { name: "質問管理", exact: true }).click();
  await page
    .getByLabel("質問本文", { exact: true })
    .first()
    .fill("更新後の自己紹介をしてください。");
  await page.getByRole("button", { name: "質問を追加", exact: true }).click();
  await page
    .getByLabel("質問本文", { exact: true })
    .last()
    .fill("追加した質問です。");
  await page
    .getByRole("combobox", { name: "カテゴリ", exact: true })
    .last()
    .click();
  await page.getByRole("option", { name: "希望条件", exact: true }).click();
  await page.getByRole("button", { name: "質問16を上へ", exact: true }).click();
  await page.getByRole("button", { name: "質問16を削除", exact: true }).click();
  await page
    .getByRole("button", { name: "保存内容を確認", exact: true })
    .click();
  await page.getByRole("button", { name: "保存して反映", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "質問一覧を保存しました",
  );
  await page.goto(oldPractice);
  await expect(
    page.getByRole("heading", {
      name: "自己紹介をお願いしてもよろしいでしょうか？",
    }),
  ).toBeVisible();
  await page.goto("/practice/");
  await page.getByRole("button", { name: "カテゴリ練習", exact: true }).click();
  await page
    .getByRole("button", { name: "自己紹介（1問）", exact: true })
    .click();
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "更新後の自己紹介をしてください。" }),
  ).toBeVisible();
  await page
    .getByLabel("あなたの回答")
    .fill("これまでの業務経験と学びについて回答します。");
  await page.getByRole("button", { name: "回答を送信", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "全1問の練習が完了しました" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "次の質問へ", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "同じ質問に再挑戦" }).click();
  await expect(page.getByLabel("あなたの回答")).toHaveValue("");
});
test("USER cannot open question management", async ({ page }) => {
  await page.goto("/admin/questions/");
  await expect(
    page.getByText("この操作を行う権限がありません。", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("質問本文", { exact: true })).toHaveCount(0);
});
for (const width of [375, 768, 899, 900, 1280])
  test(`question editor and multiline practice fit ${width}px`, async ({
    page,
  }) => {
    await page.addInitScript(() =>
      sessionStorage.setItem("pocket:mock:role", "ADMIN"),
    );
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/admin/questions/");
    await expect(page.getByLabel("質問本文", { exact: true })).toHaveCount(15);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `playwright/.cache/frontend-design-fixes/admin-${width}.png`,
      fullPage: true,
    });
    await page.screenshot({
      path: `playwright/.cache/frontend-design-fixes/admin-viewport-${width}.png`,
    });
    await page.goto("/practice/");
    await page
      .getByRole("button", { name: "カテゴリ練習", exact: true })
      .click();
    await page
      .getByRole("button", { name: "企業選び（2問）", exact: true })
      .click();
    await page
      .getByRole("button", { name: "練習を始める", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: /就職活動では/ }),
    ).toContainText("また、その軸");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `playwright/.cache/frontend-design-fixes/practice-${width}.png`,
      fullPage: true,
    });
    await page.screenshot({
      path: `playwright/.cache/frontend-design-fixes/practice-viewport-${width}.png`,
    });
  });
