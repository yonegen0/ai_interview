/** @file Input.stories.tsx @description 面接回答で使うInputの代表状態。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { Input } from "@/components/atoms/Input";
import { storyTexts } from "../../fixtures";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const meta = {
  title: "Components/Atoms/Input",
  component: Input,
  parameters: { layout: "padded" },
  decorators: [(Story) => <div style={{ width: "min(100%, 520px)" }}><Story /></div>],
  args: { label: "あなたの回答", placeholder: "回答を入力してください" },
} satisfies Meta<typeof Input>;
export default meta;
type Story = StoryObj;

export const Default: Story = {};
export const WithLabel: Story = { args: { label: "メールアドレス" } };
export const WithHelperText: Story = { args: { helperText: "100〜300文字がおすすめです" } };
export const ErrorState: Story = { args: { error: true, helperText: "空白以外の回答を入力してください" } };
export const Disabled: Story = { args: { disabled: true, defaultValue: "送信中の回答です" } };
export const Multiline: Story = { args: { multiline: true, minRows: 6 } };
export const LongText: Story = { args: { multiline: true, defaultValue: storyTexts.text1000 } };
export const KeyboardFocus: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.tab();
    await expect(within(canvasElement).getByLabelText("あなたの回答")).toHaveFocus();
  },
};
export const Mobile: Story = {
  args: { multiline: true, defaultValue: storyTexts.text500 },
  globals: { viewport: { value: "iphoneSe" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};
