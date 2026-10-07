/** @file QuestionBankPreview.stories.tsx @description Components/Organisms/Admin/QuestionBankPreviewの状態と操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { QuestionBankPreview } from "@/features/admin/components/organisms/QuestionBankPreview";
import { createBankFixture } from "../../../fixtures/refactor";
const meta = {
  title: "Components/Organisms/Admin/QuestionBankPreview",
  component: QuestionBankPreview,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { questions: createBankFixture().questions },
} satisfies Meta<typeof QuestionBankPreview>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {};
export const Multiline: Story = {
  args: {
    questions: createBankFixture(1, "一文目です。\n二文目です。").questions,
  },
};
export const MaximumLength: Story = {
  args: { questions: createBankFixture(1, "あ".repeat(1000)).questions },
};
