/** @file design.spec.ts @description デザイン修正後の画面・900px境界・入力状態・終了復旧を検証する。 */
import { test, expect, type Page } from "@playwright/test";

const widths = [375, 768, 899, 900, 1280];
const directory = "playwright/.cache/frontend-design-fixes";
async function screenshot(page: Page, name: string, width: number) {
  const main = page.locator("main");
  const offenders = await main.evaluate((element) => {
    const viewport = window.innerWidth;
    return [
      ...element.querySelectorAll(
        "h1,h2,h3,p,button,a,input,textarea,[role=combobox]",
      ),
    ]
      .filter((node) => {
        const bounds = node.getBoundingClientRect();
        return (
          bounds.width > 0 && (bounds.left < -1 || bounds.right > viewport + 1)
        );
      })
      .map((node) => node.textContent?.slice(0, 80));
  });
  expect(offenders).toEqual([]);
  await page.screenshot({
    path: `${directory}/${name}-${width}.png`,
    fullPage: true,
  });
}
async function start(page: Page) {
  await page.goto("/practice/");
  await page.getByRole("button", { name: "カテゴリ練習", exact: true }).click();
  await page.getByRole("button", { name: /^転職理由/ }).click();
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  await expect(page.getByLabel("あなたの回答")).toBeVisible();
}

for (const width of widths) {
  test(`theme and design states at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const hero = page.getByRole("heading", { level: 1 });
    await expect(hero).toHaveCSS("font-size", width >= 900 ? "44px" : "32px");
    await screenshot(page, "home", width);

    await page.goto("/login/");
    await page
      .getByRole("button", { name: "確認コードを送る", exact: true })
      .click();
    const email = page.getByLabel("メールアドレス", { exact: true });
    await expect(email).toHaveAttribute("aria-invalid", "true");
    await expect(email).toBeFocused();
    await expect(page.locator("main label").first()).toHaveCSS(
      "color",
      "rgb(179, 38, 30)",
    );
    await screenshot(page, "login-error", width);

    await page.goto("/practice/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveCSS(
      "font-size",
      width >= 900 ? "27px" : "22px",
    );
    await expect(page.locator('img[src$="mascot-welcome.webp"]')).toHaveCSS(
      "width",
      width >= 900 ? "176px" : "112px",
    );
    await screenshot(page, "practice-start", width);

    await start(page);
    const answer = page.getByLabel("あなたの回答");
    await answer.fill("あ".repeat(501));
    await expect(answer).toHaveAttribute("aria-invalid", "true");
    await expect(page.locator("main label").first()).toHaveCSS(
      "color",
      "rgb(179, 38, 30)",
    );
    await screenshot(page, "answer-error", width);
    await answer.fill(
      "これまでの経験を活かし、新しい環境で貢献したいと考えています。",
    );
    await expect(answer).toHaveAttribute("aria-invalid", "false");
    await expect(page.locator("main label").first()).toHaveCSS(
      "color",
      "rgb(65, 87, 57)",
    );
    await page.getByRole("button", { name: "練習を終了", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("入力中の下書きは破棄されます。");
    await expect(dialog.getByRole("button", { name: "続ける" })).toBeFocused();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(dialog.getByRole("button", { name: "続ける" })).toHaveCSS(
      "outline-style",
      "solid",
    );
    await page.screenshot({ path: `${directory}/exit-dialog-${width}.png` });
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("button", { name: "練習を終了", exact: true }),
    ).toBeFocused();
    await expect(answer).not.toHaveValue("");

    await page.getByRole("button", { name: "回答を送信", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "今回のフィードバック" }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "総合評価" })).toHaveCSS(
      "font-size",
      width >= 900 ? "21px" : "18px",
    );
    await screenshot(page, "feedback", width);
    await page.goto("/result/?attemptId=invalid");
    await expect(page.locator("main").getByRole("alert")).toBeVisible();
    await screenshot(page, "error", width);
  });
}

test("exit keeps an uncertain answer for reconfirmation", async ({ page }) => {
  await start(page);
  await page.evaluate(() =>
    sessionStorage.setItem("pocket:scenario", "response_lost"),
  );
  const sessionUrl = page.url();
  await page
    .getByLabel("あなたの回答")
    .fill("結果不明のまま保持する回答です。");
  await page.getByRole("button", { name: "回答を送信", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "送信結果を再確認" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "練習を終了", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "送信内容を保持して終了し",
  );
  await page.getByRole("link", { name: "未確定の送信を保持して終了" }).click();
  await expect(page).toHaveURL(/\/practice\/$/);
  await page.goto(sessionUrl);
  await expect(page.getByLabel("あなたの回答")).toHaveValue(
    "結果不明のまま保持する回答です。",
  );
  await expect(
    page.getByRole("button", { name: "送信結果を再確認" }),
  ).toBeVisible();
});

test("confirmed exit discards a draft and Escape preserves it", async ({
  page,
}) => {
  await start(page);
  const url = page.url();
  const answer = page.getByLabel("あなたの回答");
  await answer.fill("終了確認で破棄する下書きです。");
  await page.getByRole("button", { name: "練習を終了", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(answer).toHaveValue("終了確認で破棄する下書きです。");
  await page.getByRole("button", { name: "練習を終了", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "終了する", exact: true })
    .click();
  await expect(page).toHaveURL(/\/practice\/$/);
  await page.goto(url);
  await expect(page.getByLabel("あなたの回答")).toHaveValue("");
});
