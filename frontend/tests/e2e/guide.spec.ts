/** @file guide.spec.ts @description 専用ガイドの静的URL・390/1440幅・キーボード・アンカーを確認。 */
import { test, expect } from "@playwright/test";

for (const width of [390, 1440]) {
  test("guide pages fit at " + width + "px", async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await page.getByRole("link", { name: /まずは使い方ガイド/ }).click();
    await expect(page).toHaveURL(/\/guide\/$/);
    await expect(page.getByRole("heading", { name: "使い方ガイド" })).toBeVisible();

    await page.getByRole("link", { name: /基本ガイドを見る/ }).click();
    await expect(page).toHaveURL(/\/guide\/basic\/$/);
    await page.getByRole("button", { name: "次へ" }).click();
    await expect(page.getByRole("heading", { name: "自分の言葉で回答しよう" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "基本ガイド" })).toBeVisible();
    for (const [step, name] of [[1, "start"], [2, "answer"], [3, "feedback"], [4, "progress"]] as const) {
      await page.getByRole("button", { name: `STEP ${step}を表示` }).click();
      const screenshot = page.locator('img[src^="/guide/mock-"]');
      await expect(screenshot).toHaveAttribute("src", `/guide/mock-${name}.jpg`);
      await expect(screenshot).toHaveAttribute("alt", /Mock/);
      await expect.poll(() => screenshot.evaluate((image) =>
        (image as HTMLImageElement).naturalWidth
      )).toBeGreaterThan(0);
    }
    await expect(page.getByRole("link", { name: /面接練習を始める/ }))
      .toHaveAttribute("href", "/practice/quick/");

    await page.goto("/guide/features/#assist");
    const assist = page.locator("#assist");
    await expect(assist.getByRole("button", { name: /回答アシスト/ })).toHaveAttribute("aria-expanded", "true");
    await expect(assist.getByRole("heading", { name: "STAR" })).toBeVisible();
    await page.getByRole("combobox", { name: "作りたい回答" }).click();
    await page.getByRole("option", { name: "追加質問への回答" }).click();
    await expect(page.getByText(/おすすめ：深掘り回答/)).toBeVisible();

    await page.goto("/guide/features/");
    await expect(page.locator("#account").getByRole("button", { name: /アカウント・FAQ/ }))
      .toHaveAttribute("aria-expanded", "false");
    await page.locator("#account").getByRole("button", { name: /アカウント・FAQ/ }).click();
    await expect(page.getByText("途中で画面を閉じたら、回答は消えますか？")).toBeVisible();

    for (const route of ["/guide/", "/guide/basic/", "/guide/features/"]) {
      await page.goto(route);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      expect(overflow, "horizontal overflow at " + route + ", " + width + "px").toBe(false);
    }
  });
}
