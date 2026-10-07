/** @file LoginTemplate.stories.tsx @description Components/Templates/Auth/LoginTemplateの表示・フォーム状態。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { LoginPresentation } from "../../../test-utils/presentation";
const meta = {
  title: "Components/Templates/Auth/LoginTemplate",
  component: LoginPresentation,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { template: true },
} satisfies Meta<typeof LoginPresentation>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Email: Story = {};
export const Code: Story = { args: { stage: "code", cooldown: 60 } };
export const Error: Story = {
  args: { error: "コードを送信できませんでした。" },
};
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
export const Tablet: Story = { globals: { viewport: { value: "ipad" } } };
export const Desktop: Story = { globals: { viewport: { value: "desktop" } } };
