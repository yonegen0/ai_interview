/** @file QuestionBankSaveConfirmation.stories.tsx @description Components/Organisms/Admin/QuestionBankSaveConfirmationの状態と操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";
import { QuestionBankSaveConfirmation } from "@/features/admin/components/organisms/QuestionBankSaveConfirmation";

const meta = {
  title: "Components/Organisms/Admin/QuestionBankSaveConfirmation",
  component: QuestionBankSaveConfirmation,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: {
    count: 15,
    summary: { added: 1, removed: 1, edited: 1, moved: 1 },
    onPublish: fn(),
    onBack: fn(),
  },
} satisfies Meta<typeof QuestionBankSaveConfirmation>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Added: Story = {
  args: { summary: { added: 1, removed: 0, edited: 0, moved: 0 } },
};
export const Removed: Story = {
  args: { summary: { added: 0, removed: 1, edited: 0, moved: 0 } },
};
export const Edited: Story = {
  args: { summary: { added: 0, removed: 0, edited: 1, moved: 0 } },
};
export const Moved: Story = {
  args: { summary: { added: 0, removed: 0, edited: 0, moved: 1 } },
};
export const Combined: Story = {};
export const Saving: Story = { args: { saving: true } };
