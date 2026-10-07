/** @file ChoiceButton.stories.tsx @description Components/Atoms/ChoiceButtonの状態と操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";
import { ChoiceButton } from "@/components/atoms/ChoiceButton";
import { expect, userEvent, within } from "storybook/test";
const meta = {
  title: "Components/Atoms/ChoiceButton",
  component: ChoiceButton,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { children: "カテゴリ練習", onClick: fn() },
} satisfies Meta<typeof ChoiceButton>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {};
export const Selected: Story = { args: { selected: true } };
export const Disabled: Story = { args: { disabled: true } };
export const LongText: Story = {
  args: { children: "長い選択肢を表示して折返しと読みやすさを確認します。" },
};
export const Keyboard: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    await expect(within(canvasElement).getByRole("button")).toHaveFocus();
    await expect(meta.args.onClick).toHaveBeenCalled();
  },
};
