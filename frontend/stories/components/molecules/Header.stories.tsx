/** @file Header.stories.tsx @description 面接アプリ用Headerの文言と幅の確認。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Header } from "@/components/molecules/Header";
import { storyTexts } from "../../fixtures";

const meta = {
  title: "Components/Molecules/Header",
  component: Header,
  parameters: { layout: "padded" },
  args: { eyebrow: "QUICK PRACTICE", title: "面接練習", description: "一問ずつ、自分の経験を言葉にする練習を始めましょう。" },
} satisfies Meta<typeof Header>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Full: Story = {};
export const NoEyebrow: Story = { args: { eyebrow: undefined, title: "フィードバック" } };
export const TitleOnly: Story = { args: { eyebrow: undefined, title: "練習を終了", description: undefined } };
export const LongDescription: Story = { args: { description: storyTexts.text500 } };
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
