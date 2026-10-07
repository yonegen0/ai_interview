/** @file QuestionEditorList.stories.tsx @description Components/Organisms/Admin/QuestionEditorListの表示・フォーム状態。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AdminPresentation } from "../../../test-utils/presentation";
const meta = {
  title: "Components/Organisms/Admin/QuestionEditorList",
  component: AdminPresentation,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { kind: "list" },
} satisfies Meta<typeof AdminPresentation>;
export default meta;
type Story = StoryObj<typeof meta>;
export const One: Story = { args: { count: 1 } };
export const Fifteen: Story = {};
export const Hundred: Story = { args: { count: 100 } };
export const Empty: Story = { args: { count: 0 } };
