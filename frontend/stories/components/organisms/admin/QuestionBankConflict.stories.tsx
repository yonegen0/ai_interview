/** @file QuestionBankConflict.stories.tsx @description Components/Organisms/Admin/QuestionBankConflictの状態と操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";
import { QuestionBankConflict } from "@/features/admin/components/organisms/QuestionBankConflict";
import {
  createBankFixture,
  createDraftFixture,
} from "../../../fixtures/refactor";
const meta = {
  title: "Components/Organisms/Admin/QuestionBankConflict",
  component: QuestionBankConflict,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: {
    active: true,
    comparison: createBankFixture(),
    questions: createBankFixture(1, "今回の編集です。").questions,
    previousDraft: null,
    onFetchLatest: fn(),
    onAdoptLatest: fn(),
  },
} satisfies Meta<typeof QuestionBankConflict>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Compared: Story = {};
export const FetchFailure: Story = { args: { comparison: null } };
export const PreviousEdit: Story = {
  args: { active: false, previousDraft: createDraftFixture() },
};
export const LongComparison: Story = {
  args: { comparison: createBankFixture(1, "長い本文です。".repeat(100)) },
};
