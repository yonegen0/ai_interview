/** @file QuestionEditorCard.stories.tsx @description Components/Molecules/Admin/QuestionEditorCardの表示・フォーム状態。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AdminPresentation } from "../../../test-utils/presentation";
import { storyTexts } from "../../../fixtures";
import { expect, within } from "storybook/test";
import { theme } from "@/theme/theme";
const meta = {
  title: "Components/Molecules/Admin/QuestionEditorCard",
  component: AdminPresentation,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { kind: "card", count: 2 },
} satisfies Meta<typeof AdminPresentation>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const move = canvas.getByRole("button", { name: "質問1を下へ" });
    await expect(move).toHaveStyle({
      color: theme.palette.primary.main,
      borderStyle: "solid",
    });
    await expect(move).not.toHaveStyle({
      backgroundColor: theme.palette.primary.main,
    });
    await expect(
      canvas.getByRole("button", { name: "質問1を削除" }),
    ).toHaveStyle({ color: theme.palette.error.main });
  },
};
export const Empty: Story = { args: { text: "" } };
export const LongText: Story = { args: { text: storyTexts.text1000 } };
export const Multiline: Story = {
  args: { text: "一文目です。\n二文目です。" },
};
export const Invalid: Story = { args: { inputError: true, text: " " } };
export const First: Story = {};
export const Last: Story = { args: { last: true } };
export const Disabled: Story = { args: { disabled: true } };
