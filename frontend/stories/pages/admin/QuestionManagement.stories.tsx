/** @file QuestionManagement.stories.tsx @description 管理者質問一覧と保存操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within, waitFor } from "storybook/test";
import { QuestionManagement } from "@/features/admin/components/pages/QuestionManagement";
import { http, HttpResponse } from "msw";
import { createBankFixture, createDraftFixture } from "../../fixtures/refactor";
import { storyIds } from "../../fixtures";
const bank = createBankFixture();
const draft = createDraftFixture();
draft.questions[0].question = "復元した編集です。";
const stored = { baseline: bank, draft };
const editFirst = async (canvasElement: HTMLElement) => {
  const canvas = within(canvasElement);
  const input = (await canvas.findAllByLabelText("質問本文"))[0];
  await userEvent.clear(input);
  await userEvent.type(input, "編集した質問です。");
  return canvas;
};
const meta = {
  title: "Pages/Admin/QuestionManagement",
  component: QuestionManagement,
  parameters: {
    mock: true,
    mockRole: "ADMIN",
    initialRoute: "/admin/questions/",
  },
} satisfies Meta<typeof QuestionManagement>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Initial: Story = {};
export const EditedAndSaved: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const text = (await canvas.findAllByLabelText("質問本文"))[0];
    await userEvent.clear(text);
    await userEvent.type(text, "変更した質問です。");
    await userEvent.click(
      canvas.getByRole("button", { name: "保存内容を確認" }),
    );
    await userEvent.click(canvas.getByRole("button", { name: "保存して反映" }));
    await expect(
      await canvas.findByText(/質問一覧を保存しました/),
    ).toHaveTextContent("質問一覧を保存しました");
  },
};
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };

export const Unchanged: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByLabelText("質問本文");
    await expect(
      canvas.getByRole("button", { name: "保存内容を確認" }),
    ).toBeDisabled();
  },
};
export const InvalidQuestion: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.clear((await canvas.findAllByLabelText("質問本文"))[0]);
    await expect(
      canvas.getByRole("button", { name: "保存内容を確認" }),
    ).toBeDisabled();
    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "1〜1,000",
    );
  },
};
export const ConfirmLocksEditing: Story = {
  play: async ({ canvasElement }) => {
    const canvas = await editFirst(canvasElement);
    await userEvent.click(
      canvas.getByRole("button", { name: "保存内容を確認" }),
    );
    for (const input of canvas.getAllByLabelText("質問本文"))
      await expect(input).toBeDisabled();
    await userEvent.click(canvas.getByRole("button", { name: "編集に戻る" }));
    await expect(canvas.getAllByLabelText("質問本文")[0]).toBeEnabled();
  },
};
export const AddMoveDelete: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findAllByLabelText("質問本文");
    await userEvent.click(canvas.getByRole("button", { name: "質問を追加" }));
    await expect(canvas.getAllByLabelText("質問本文")).toHaveLength(16);
    await userEvent.type(
      canvas.getAllByLabelText("質問本文")[15],
      "追加した質問です。",
    );
    await userEvent.click(canvas.getByRole("button", { name: "質問16を上へ" }));
    await expect(canvas.getAllByLabelText("質問本文")[14]).toHaveValue(
      "追加した質問です。",
    );
    await userEvent.click(canvas.getByRole("button", { name: "質問15を削除" }));
    await expect(canvas.getAllByLabelText("質問本文")).toHaveLength(15);
  },
};
export const CancelEdits: Story = {
  play: async ({ canvasElement }) => {
    const canvas = await editFirst(canvasElement);
    await userEvent.click(
      canvas.getByRole("button", { name: "変更を取り消す" }),
    );
    await expect(
      canvas.getByRole("button", { name: "保存内容を確認" }),
    ).toBeDisabled();
  },
};
export const RestoredDraft: Story = {
  parameters: { storage: { "pocket:admin:question-bank": stored } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() =>
      expect(canvas.getAllByLabelText("質問本文")[0]).toHaveValue(
        "復元した編集です。",
      ),
    );
  },
};
export const RestoredPending: Story = {
  parameters: {
    storage: {
      "pocket:admin:question-bank": {
        ...stored,
        pending: { key: storyIds.idempotency, body: draft },
      },
    },
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      await canvas.findByRole("button", { name: "保存結果を再確認" }),
    ).toBeVisible();
    await expect(canvas.getAllByLabelText("質問本文")[0]).toBeDisabled();
  },
};
export const ResponseLostAndReconfirmed: Story = {
  parameters: { mockScenario: "response_lost" },
  play: async ({ canvasElement }) => {
    const canvas = await editFirst(canvasElement);
    await userEvent.click(
      canvas.getByRole("button", { name: "保存内容を確認" }),
    );
    await userEvent.click(canvas.getByRole("button", { name: "保存して反映" }));
    await userEvent.click(
      await canvas.findByRole("button", { name: "保存結果を再確認" }),
    );
    await expect(
      await canvas.findByText(/質問一覧を保存しました/),
    ).toHaveTextContent("質問一覧を保存しました");
  },
};
export const Conflict: Story = {
  parameters: {
    handlers: [
      http.post("*/api/admin/question-bank", () =>
        HttpResponse.json(
          { code: "QUESTION_BANK_CONFLICT", message: "conflict" },
          { status: 409 },
        ),
      ),
    ],
  },
  play: async ({ canvasElement }) => {
    const canvas = await editFirst(canvasElement);
    await userEvent.click(
      canvas.getByRole("button", { name: "保存内容を確認" }),
    );
    await userEvent.click(canvas.getByRole("button", { name: "保存して反映" }));
    await expect(
      await canvas.findByRole("heading", { name: "最新版との比較" }),
    ).toBeVisible();
    await userEvent.click(
      await canvas.findByRole("button", { name: "最新版で編集し直す" }),
    );
    await expect(
      canvas.getByRole("heading", { name: "変更前の編集内容（参照用）" }),
    ).toBeVisible();
    await expect(canvas.getByText("1. 編集した質問です。")).toBeVisible();
  },
};
export const Forbidden: Story = {
  parameters: { mockRole: "USER" },
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole("alert"),
    ).toHaveTextContent("権限がありません");
  },
};
export const Tablet: Story = { globals: { viewport: { value: "ipad" } } };
export const Desktop: Story = { globals: { viewport: { value: "desktop" } } };
