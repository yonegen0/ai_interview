/** @file StarAssist.stories.tsx @description STAR初期入力と各案編集のStory受入。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";
import { PracticeSessionContent } from "@/features/interview/components/pages/PracticeSessionContent";
import { createSessionFixture, createStoryState } from "../../fixtures";
import { questions } from "@/mocks/data/questions";
const session = createSessionFixture({ question: questions[3] });
const meta = {
  title: "Pages/Interview/StarAssist",
  component: PracticeSessionContent,
  parameters: {
    mock: true,
    seed: createStoryState({ session }),
    layout: "padded",
  },
  args: { session, retryFrom: null },
} satisfies Meta<typeof PracticeSessionContent>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Initial: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      canvas.getByRole("button", { name: /エピソード作成アシスト/ }),
    );
    const dialog = within(document.body);
    await waitFor(() =>
      expect(dialog.getByRole("dialog", { name: /エピソード作成アシスト/ })).toBeVisible(),
    );
    await userEvent.click(dialog.getByRole("button", { name: "次へ" }));
    await userEvent.click(dialog.getByRole("button", { name: "次へ" }));
    await expect(dialog.getByLabelText("A 本人の行動")).toBeVisible();
    await userEvent.click(dialog.getByRole("button", { name: "次へ" }));
    await expect(dialog.getByRole("button", { name: "3案を生成（1回）" })).toBeDisabled();
  },
};
