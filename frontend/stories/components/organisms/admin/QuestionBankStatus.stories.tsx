/** @file QuestionBankStatus.stories.tsx @description Components/Organisms/Admin/QuestionBankStatusの状態と操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";
import { QuestionBankStatus } from "@/features/admin/components/organisms/QuestionBankStatus";

const meta = {
  title: "Components/Organisms/Admin/QuestionBankStatus",
  component: QuestionBankStatus,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: {
    loading: false,
    stage: "editable",
    error: null,
    message: "",
    onRefresh: fn(),
    onReconfirm: fn(),
  },
} satisfies Meta<typeof QuestionBankStatus>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Loading: Story = { args: { loading: true } };
export const Success: Story = {
  args: {
    stage: "success",
    message: "質問一覧を保存しました（15問）。次の新規練習から反映します。",
  },
};
export const FetchFailure: Story = {
  args: { error: new Error("取得できませんでした。") },
};
export const Saving: Story = { args: { stage: "saving" } };
export const Uncertain: Story = { args: { stage: "uncertain" } };
export const Forbidden: Story = { args: { stage: "forbidden" } };
