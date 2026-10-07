/** @file Text.stories.tsx @description Components/Atoms/Textの状態と操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Text } from "@/components/atoms/Text";

const meta = {
  title: "Components/Atoms/Text",
  component: Text,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { children: "本文を表示します。" },
} satisfies Meta<typeof Text>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Body: Story = {};
export const Heading: Story = { args: { variant: "h1", component: "h1" } };
export const Caption: Story = { args: { variant: "caption" } };
export const Status: Story = {
  args: { role: "status", "aria-live": "polite" },
};
export const Multiline: Story = {
  args: { children: "一文目です。\n二文目です。" },
};
export const LongText: Story = {
  args: { children: "長い文章の折返しを確認します。".repeat(40) },
};
