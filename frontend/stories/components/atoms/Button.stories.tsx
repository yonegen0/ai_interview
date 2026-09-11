/** @file Button.stories.tsx @description 共通Buttonの状態、キーボード操作、狭幅表示。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { Button } from "@/components/atoms/Button";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const meta = {
  title: "Components/Atoms/Button",
  component: Button,
  parameters: { layout: "padded" },
  args: { children: "回答を送信", onClick: fn() },
} satisfies Meta<typeof Button>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = { args: { variant: "contained", color: "primary" } };
export const Secondary: Story = { args: { variant: "contained", color: "secondary" } };
export const Success: Story = { args: { color: "success", children: "次の質問へ" } };
export const Destructive: Story = { args: { color: "error", children: "終了する" } };
export const Outlined: Story = { args: { variant: "outlined" } };
export const Disabled: Story = {
  args: { disabled: true },
  play: async ({ args, canvasElement }) => {
    within(canvasElement).getByRole("button").click();
    await expect(args.onClick).not.toHaveBeenCalled();
  },
};
export const KeyboardActivation: Story = {
  play: async ({ args, canvasElement }) => {
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    await expect(args.onClick).toHaveBeenCalledOnce();
    await expect(within(canvasElement).getByRole("button")).toHaveFocus();
  },
};
export const LongLabel: Story = {
  args: { children: "送信済みの回答について評価結果をもう一度確認する" },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};
export const Mobile: Story = {
  ...LongLabel,
  globals: { viewport: { value: "iphoneSe" } },
};
