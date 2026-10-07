/** @file AnswerSubmission.stories.tsx @description Components/Organisms/Interview/AnswerSubmissionの表示・フォーム状態。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AnswerPresentation } from "../../../test-utils/presentation";
import { storyTexts } from "../../../fixtures";
const meta = {
  title: "Components/Organisms/Interview/AnswerSubmission",
  component: AnswerPresentation,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: {},
} satisfies Meta<typeof AnswerPresentation>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Empty: Story = {};
export const Answering: Story = { args: { text: "回答です。" } };
export const MaximumLength: Story = { args: { text: storyTexts.text500 } };
export const Invalid: Story = {
  args: { text: " ", inputError: "空白以外の回答を入力してください。" },
};
export const Submitting: Story = {
  args: { text: "回答です。", phase: "submitting" },
};
export const Uncertain: Story = {
  args: { text: "回答です。", phase: "recovery_required" },
};
