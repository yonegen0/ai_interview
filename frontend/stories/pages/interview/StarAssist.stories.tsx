/** @file StarAssist.stories.tsx @description STAR初期入力と各案編集のStory受入。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { PracticeSessionContent } from "@/features/interview/components/pages/PracticeSessionContent";
import { createSessionFixture, createStoryState } from "../../fixtures";
const session = createSessionFixture();
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
      canvas.getByRole("button", { name: "STARアシストを開く" }),
    );
    await expect(canvas.getByLabelText("A 本人の行動")).toBeVisible();
    await expect(
      canvas.getByRole("button", { name: "3案を生成（1回）" }),
    ).toBeDisabled();
  },
};
