/** @file star-assist.spec.ts @description Real shared IndexedDB STAR save, edit, recovery and owner guards. */
import { test, expect, type Page } from "@playwright/test";
import type { MockState } from "../../src/mocks/store";
import legacyQuestions from "../../src/mocks/data/legacy-questions.json";
for (const version of [1, 2])
  test(`T19 imports V${version} exactly once without replacing legacy keys`, async ({
    page,
  }) => {
    await page.goto("/");
    const sid = crypto.randomUUID(),
      key = crypto.randomUUID();
    const pool = legacyQuestions.filter((q) => q.category === "job_change");
    const raw = JSON.stringify({
      version,
      sessions: {
        [sid]: {
          sessionId: sid,
          question: pool[0],
          questionNumber: 1,
          activeAttempt: null,
        },
      },
      attempts: {},
      requests: {
        [key]: {
          fingerprint: "legacy-snapshot",
          status: 201,
          body: { sessionId: sid },
        },
      },
      consumed: [],
      ...(version === 2
        ? { sessionQuestions: { [sid]: pool }, owners: { [sid]: "mock-user" } }
        : {}),
    });
    await page.evaluate(
      ({ version, raw }) =>
        new Promise<void>((resolve, reject) => {
          sessionStorage.setItem(`pocket:mock:v${version}`, raw);
          const open = indexedDB.open("pocket:mock:v4", 1);
          open.onupgradeneeded = () => open.result.createObjectStore("state");
          open.onsuccess = () => {
            const db = open.result,
              tx = db.transaction("state", "readwrite");
            tx.objectStore("state").delete("current");
            tx.oncomplete = () => {
              db.close();
              resolve();
            };
            tx.onabort = () => reject(tx.error);
          };
        }),
      { version, raw },
    );
    await page.goto(`/practice/session/?sessionId=${sid}`);
    await expect(
      page.getByRole("heading", { name: pool[0].question, exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("あなたの回答")).toHaveValue("");
    await page.getByLabel("あなたの回答").fill("旧版から引き継いだ保存です。");
    await expect(
      page.getByRole("status").filter({ hasText: "下書き：" }),
    ).toContainText("保存済");
    await page.reload();
    await expect(page.getByLabel("あなたの回答")).toHaveValue(
      "旧版から引き継いだ保存です。",
    );
    expect(
      await page.evaluate(
        (version) => sessionStorage.getItem(`pocket:mock:v${version}`),
        version,
      ),
    ).toBe(raw);
  });
test("T06 lost save receipt remains identifiable after another tab updates", async ({
  page,
  context,
}) => {
  await begin(page);
  await page.evaluate(() =>
    sessionStorage.setItem("pocket:scenario", "star_response_lost"),
  );
  await page
    .getByLabel("あなたの回答")
    .fill("応答消失前に保存した本人入力です。");
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存失敗");
  const second = await context.newPage();
  await second.goto(page.url());
  await expect(second.getByLabel("あなたの回答")).toHaveValue(
    "応答消失前に保存した本人入力です。",
  );
  await second.getByLabel("あなたの回答").fill("別タブが後から保存しました。");
  await expect(
    second.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await page.getByRole("button", { name: "保存結果を再確認" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("競合");
  await expect(page.getByLabel("あなたの回答")).toHaveValue(
    "応答消失前に保存した本人入力です。",
  );
  await page.getByRole("button", { name: "保存版を確認", exact: true }).click();
  await expect(
    page.getByText("現在の保存版：別タブが後から保存しました。", {
      exact: true,
    }),
  ).toBeVisible();
});

test("T15 application response cannot replace typing during apply", async ({
  page,
}) => {
  await begin(page);
  await generate(page);
  await page.getByRole("radio", { name: "案Aを選択" }).check();
  await page.getByLabel("あなたの回答").fill("確認前の既存入力です。");
  await page.waitForTimeout(1200);
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await page.evaluate(() =>
    sessionStorage.setItem("pocket:scenario", "star_apply_delayed"),
  );
  await page.getByRole("button", { name: "この回答を反映" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("あなたの回答")).toHaveValue(
    "確認前の既存入力です。",
  );
  await page.getByRole("button", { name: "この回答を反映" }).click();
  await page.getByRole("button", { name: "置き換える", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存中");
  await page
    .getByLabel("あなたの回答")
    .fill("反映の通信中に本人が入力した内容です。");
  await expect(page.getByLabel("あなたの回答")).toHaveValue(
    "反映の通信中に本人が入力した内容です。",
  );
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await page.reload();
  await expect(page.getByLabel("あなたの回答")).toHaveValue(
    "反映の通信中に本人が入力した内容です。",
  );
});
async function begin(page: Page) {
  await page.goto("/practice/");
  await page.getByRole("button", { name: "カテゴリ練習", exact: true }).click();
  await page.getByRole("button", { name: /^転職理由/ }).click();
  await page.getByRole("button", { name: "練習を始める", exact: true }).click();
  await expect(page.getByLabel("あなたの回答")).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
}
async function generate(page: Page) {
  await page.getByRole("button", { name: "STARアシストを開く" }).click();
  await page.getByRole("combobox", { name: "応募先カテゴリ" }).click();
  await page.getByRole("option", { name: "法人営業", exact: true }).click();
  await page.getByLabel("A 本人の行動").fill("私は顧客の課題を整理しました。");
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await page.getByRole("button", { name: "3案を生成（1回）" }).click();
  await expect(page.getByLabel("案Aの回答")).toBeVisible();
}
for (const width of [375, 768, 1280])
  test(`T15/T21/T22 ${width}px three editable choices and apply without evaluation`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await begin(page);
    await generate(page);
    await page
      .getByLabel("案Aの回答")
      .fill("本人が選択前に編集した回答Aです。");
    await page
      .getByLabel("案Bの回答")
      .fill("本人が選択前に編集した回答Bです。");
    await page
      .getByLabel("案Cの回答")
      .fill("本人が選択前に編集した回答Cです。");
    await page.getByRole("radio", { name: "案Bを選択" }).check();
    await page.getByRole("radio", { name: "案Aを選択" }).check();
    await expect(page.getByLabel("案Bの回答")).toHaveValue(
      "本人が選択前に編集した回答Bです。",
    );
    await page.getByRole("button", { name: "この回答を反映" }).click();
    await expect(page.getByLabel("あなたの回答")).toHaveValue(
      "本人が選択前に編集した回答Aです。",
    );
    await expect(
      page.getByRole("button", { name: "回答を送信", exact: true }),
    ).toBeEnabled();
    const count = await page.evaluate(
      () =>
        new Promise<number>((resolve, reject) => {
          const opening = indexedDB.open("pocket:mock:v4", 1);
          opening.onsuccess = () => {
            const db = opening.result;
            const request = db
              .transaction("state")
              .objectStore("state")
              .get("current");
            request.onsuccess = () => {
              resolve(Object.keys(request.result.state.evaluations).length);
              db.close();
            };
            request.onerror = () => reject(request.error);
          };
        }),
    );
    expect(count).toBe(0);
    await page.getByLabel("案Aの回答").focus();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("案Bの回答")).toBeFocused();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`star-v14-${width}.png`),
      fullPage: true,
    });
  });

test("T03 new server-bound local cache cannot restore expired answer", async ({
  page,
}) => {
  await begin(page);
  await page.getByLabel("あなたの回答").fill("期限切れにする保存本文です。");
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await page.waitForTimeout(300);
  await page.evaluate(
    () =>
      new Promise<void>((resolve, reject) => {
        const opening = indexedDB.open("pocket:mock:v4", 1);
        opening.onsuccess = () => {
          const db = opening.result,
            tx = db.transaction("state", "readwrite"),
            store = tx.objectStore("state"),
            get = store.get("current");
          get.onsuccess = () => {
            const envelope = get.result as { state: MockState };
            for (const row of Object.values(envelope.state.star.answers))
              row.value.expiresAt = 1;
            store.put(envelope, "current");
          };
          tx.oncomplete = () => {
            db.close();
            resolve();
          };
          tx.onabort = () => reject(tx.error);
        };
      }),
  );
  await page.reload();
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await expect(page.getByLabel("あなたの回答")).toHaveValue("");
});
test("T20 close tab restores server draft and STAR edits", async ({
  page,
  context,
}) => {
  await begin(page);
  await generate(page);
  await page.getByLabel("案Cの回答").fill("閉タブから復元する回答Cです。");
  await page.getByLabel("あなたの回答").fill("通常下書きも復元します。");
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await page.waitForTimeout(1200);
  const url = page.url();
  await page.close();
  const next = await context.newPage();
  await next.goto(url);
  await expect(next.getByLabel("あなたの回答")).toHaveValue(
    "通常下書きも復元します。",
  );
  await next.getByRole("button", { name: "STARアシストを開く" }).click();
  await expect(next.getByLabel("案Cの回答")).toHaveValue(
    "閉タブから復元する回答Cです。",
  );
});
test("T05/T08 two tabs conflict and formal send rejects stale save", async ({
  page,
  context,
}) => {
  await begin(page);
  await page.getByLabel("あなたの回答").fill("最初の保存です。");
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  const second = await context.newPage();
  await second.goto(page.url());
  await expect(second.getByLabel("あなたの回答")).toHaveValue(
    "最初の保存です。",
  );
  await page.getByLabel("あなたの回答").fill("第一タブからの変更です。");
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await second.getByLabel("あなたの回答").fill("第二タブの内容を保持します。");
  await expect(
    second.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("競合");
  await page.getByRole("button", { name: "回答を送信", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "今回のフィードバック", exact: true }),
  ).toBeVisible();
  await expect(second.getByLabel("あなたの回答")).toHaveValue(
    "第二タブの内容を保持します。",
  );
});

test("T23 unchanged answer and STAR issue zero draft saves", async ({
  page,
}) => {
  const saves: string[] = [];
  page.on("request", (request) => {
    if (
      ["POST", "PUT"].includes(request.method()) &&
      /\/(answer-drafts|star-drafts)(\/|$)/.test(request.url())
    )
      saves.push(request.url());
  });
  await begin(page);
  await page.waitForTimeout(2100);
  expect(saves).toHaveLength(0);
});

test("T19 V4 keeps legacy source and stops on corruption", async ({ page }) => {
  await begin(page);
  const legacy = await page.evaluate(
    () =>
      new Promise<string>((resolve) => {
        const open = indexedDB.open("pocket:mock:v4", 1);
        open.onsuccess = () => {
          const db = open.result,
            tx = db.transaction("state", "readwrite"),
            store = tx.objectStore("state"),
            read = store.get("current");
          read.onsuccess = () => {
            const raw = JSON.stringify(read.result.state);
            sessionStorage.setItem("pocket:mock:v3", raw);
            store.delete("current");
            resolve(raw);
          };
          tx.oncomplete = () => db.close();
        };
      }),
  );
  await page.reload();
  await expect(page.getByLabel("あなたの回答")).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("pocket:mock:v3")),
  ).toBe(legacy);
  await page.getByLabel("あなたの回答").fill("移行後の新しい保存です。");
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await page.reload();
  await expect(page.getByLabel("あなたの回答")).toHaveValue(
    "移行後の新しい保存です。",
  );
  const oldTab = JSON.parse(legacy) as MockState;
  oldTab.consumed.push("old-tab-unmerged");
  const unmerged = JSON.stringify(oldTab);
  await page.evaluate(
    (raw) => sessionStorage.setItem("pocket:mock:v3", raw),
    unmerged,
  );
  await page.reload();
  await expect(page.getByLabel("あなたの回答")).toHaveValue(
    "移行後の新しい保存です。",
  );
  await expect(
    page.getByText(
      "未統合の旧体験版データがあります。元データは保持しています。",
      { exact: true },
    ),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("pocket:mock:v3")),
  ).toBe(unmerged);
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        const open = indexedDB.open("pocket:mock:v4", 1);
        open.onsuccess = () => {
          const db = open.result,
            tx = db.transaction("state", "readwrite");
          tx.objectStore("state").put(
            { version: 4, sourceHash: null, state: {} },
            "current",
          );
          tx.oncomplete = () => {
            db.close();
            resolve();
          };
        };
      }),
  );
  await page.reload();
  await expect(page.getByLabel("あなたの回答")).not.toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("pocket:mock:v3")),
  ).toBe(unmerged);
});

test("T20 owner switch cannot restore another person's drafts", async ({
  page,
}) => {
  await begin(page);
  const url = page.url();
  await page.getByLabel("あなたの回答").fill("元の本人だけの保存です。");
  await expect(
    page.getByRole("status").filter({ hasText: "下書き：" }),
  ).toContainText("保存済");
  await page.evaluate(() =>
    sessionStorage.setItem(
      "pocket:mock:identity",
      JSON.stringify({ sub: "different-owner", groups: ["USER"] }),
    ),
  );
  await page.reload();
  await expect(page.getByLabel("あなたの回答")).not.toBeVisible();
  await page.evaluate(() =>
    sessionStorage.setItem(
      "pocket:mock:identity",
      JSON.stringify({ sub: "mock-user", groups: ["USER"] }),
    ),
  );
  await page.goto(url);
  await expect(page.getByLabel("あなたの回答")).toHaveValue(
    "元の本人だけの保存です。",
  );
});
