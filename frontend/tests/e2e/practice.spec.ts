/** @file practice.spec.ts @description 静的成果物上の主要ユーザーフロー */
import { test, expect, type Page } from "@playwright/test";
const begin = async (page: Page) => {
  await page.goto("/practice/");
  await page.getByRole("button", { name: "転職理由", exact: true }).click();
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  await expect(page.getByLabel("あなたの回答")).toBeVisible();
};
const answer = async (page: Page) => {
  await page
    .getByLabel("あなたの回答")
    .fill("業務改善の経験を活かして、新しい環境で貢献したいと考えています。");
  await page.getByRole("button", { name: "回答を送信", exact: true }).click();
};
test("normal, retry, next, direct result and browser navigation", async ({
  page,
}) => {
  await begin(page);
  await answer(page);
  await expect(
    page.getByRole("heading", { name: "今回のフィードバック" }),
  ).toBeVisible();
  const firstResult = page.url();
  await expect(page.getByRole("heading", { name: "次の練習へ" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "次の質問へ", exact: true }),
  ).toHaveCount(1);
  await page.getByRole("link", { name: "同じ質問に再挑戦" }).click();
  await expect(page.getByLabel("あなたの回答")).toHaveValue("");
  await answer(page);
  await expect(
    page.getByRole("heading", { name: "今回のフィードバック" }),
  ).toBeVisible();
  expect(page.url()).not.toBe(firstResult);
  await page.getByRole("button", { name: "次の質問へ", exact: true }).click();
  await expect(page.getByText(/QUESTION 02/)).toBeVisible();
  await page.goBack();
  await expect(
    page.getByRole("link", { name: "現在の練習へ戻る" }),
  ).toBeVisible();
  await page.goForward();
  await expect(page.getByText(/QUESTION 02/)).toBeVisible();
  await page.goto(firstResult);
  await expect(
    page.getByRole("heading", { name: "今回のフィードバック" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "次の質問へ", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "次の練習へ" })).toHaveCount(
    0,
  );
  await expect(page.locator('img[src$="mascot-retry.webp"]')).toHaveCount(0);
});
test("response loss recovers without duplicate attempt", async ({ page }) => {
  await begin(page);
  await page.evaluate(() =>
    sessionStorage.setItem("pocket:scenario", "response_lost"),
  );
  await answer(page);
  await expect(
    page.getByRole("button", { name: "送信結果を再確認" }),
  ).toBeVisible();
  await expect(page.getByLabel("あなたの回答")).toBeDisabled();
  await page.getByRole("button", { name: "送信結果を再確認" }).click();
  await expect(
    page.getByRole("heading", { name: "今回のフィードバック" }),
  ).toBeVisible();
  const count = await page.evaluate(
    () =>
      Object.keys(
        JSON.parse(sessionStorage.getItem("pocket:mock:v1")!).attempts,
      ).length,
  );
  expect(count).toBe(1);
});
test("reload during processing resumes evaluation", async ({ page }) => {
  page.on("dialog", (dialog) => dialog.accept());
  await begin(page);
  await answer(page);
  await expect(
    page.getByRole("heading", { name: "回答を確認しています" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "今回のフィードバック" }),
  ).toBeVisible();
});
test("draft reload and invalid IDs", async ({ page }) => {
  page.on("dialog", (dialog) => dialog.accept());
  await begin(page);
  await page.getByLabel("あなたの回答").fill("保存する下書き");
  await page.reload();
  await expect(page.getByLabel("あなたの回答")).toHaveValue("保存する下書き");
  await page.goto("/result/?attemptId=invalid");
  await expect(page.getByText("回答IDを確認してください。")).toBeVisible();
  await page.goto(
    "/practice/session/?sessionId=00000000-0000-4000-8000-000000000099",
  );
  await expect(page.getByText("練習が見つかりません。")).toBeVisible();
});

test("mascot assets are static and image failures do not block practice", async ({
  page,
}) => {
  const imageRequests: string[] = [];
  page.on("request", (request) => {
    if (request.resourceType() === "image") imageRequests.push(request.url());
  });
  const imageResponse = page.waitForResponse((response) =>
    response.url().endsWith("/images/mascot/mascot-welcome.webp"),
  );
  await page.goto("/practice/");
  expect((await imageResponse).headers()["content-type"]).toBe("image/webp");
  const welcome = page.locator('img[src$="mascot-welcome.webp"]');
  await expect(welcome).toBeVisible();
  await expect
    .poll(() =>
      welcome.evaluate((image: HTMLImageElement) => image.naturalWidth),
    )
    .toBe(512);
  const dimensions = await welcome.locator("..").boundingBox();
  await page.route("**/images/mascot/*.webp", (route) => route.abort());
  await page.reload();
  await expect(welcome).toBeHidden();
  const failedDimensions = await welcome.locator("..").boundingBox();
  expect(failedDimensions?.width).toBe(dimensions?.width);
  expect(failedDimensions?.height).toBe(dimensions?.height);
  await page.getByRole("button", { name: "転職理由", exact: true }).click();
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  await answer(page);
  await expect(
    page.getByRole("heading", { name: "今回のフィードバック" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "同じ質問に再挑戦" }).click();
  await expect(page.getByLabel("あなたの回答")).toBeEnabled();
  expect(imageRequests.some((url) => url.includes("/_next/image"))).toBe(false);
  expect(imageRequests.some((url) => url.endsWith("mascot-welcome.webp"))).toBe(
    true,
  );
});

const expectContentWithinViewport = async (page: Page) => {
  const overflowing = await page.locator("main").evaluate((main) =>
    [
      ...main.querySelectorAll(
        "img, h1, h2, p, button, a, textarea, [role='alert']",
      ),
    ]
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return (
          rect.width > 0 &&
          (rect.left < -1 || rect.right > window.innerWidth + 1)
        );
      })
      .map((element) => element.tagName),
  );
  expect(overflowing).toEqual([]);
};
for (const width of [375, 768, 1280])
  test(`layout ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/practice/");
    await expect(page.locator('img[src$="mascot-welcome.webp"]')).toBeVisible();
    await expectContentWithinViewport(page);
    await begin(page);
    await expect(page.locator("main img")).toHaveCount(0);
    const field = page.getByLabel("あなたの回答");
    await field.fill("😀".repeat(250));
    await expect(page.getByText("500 / 500文字 · 100〜300文字がおすすめです")).toBeVisible();
    await expectContentWithinViewport(page);
    await field.fill("😀".repeat(250) + "あ");
    await expect(page.getByText("500文字以内で入力してください。")).toBeVisible();
    await expect(field).toHaveValue("😀".repeat(250) + "あ");
    await expect(page.getByRole("button", { name: "回答を送信", exact: true })).toBeDisabled();
    await expectContentWithinViewport(page);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await field.fill("あ".repeat(500));
    await page.getByRole("button", { name: "回答を送信", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "回答を確認しています" }),
    ).toBeVisible();
    await expectContentWithinViewport(page);
    await expect(
      page.getByRole("heading", { name: "今回のフィードバック" }),
    ).toBeVisible();
    await expectContentWithinViewport(page);
    await page.goto("/result/?attemptId=invalid");
    await expect(page.locator("main").getByRole("alert")).toBeVisible();
    await expectContentWithinViewport(page);
  });
