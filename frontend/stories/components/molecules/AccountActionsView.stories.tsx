/** @file AccountActionsView.stories.tsx @description Components/Molecules/AccountActionsViewの状態と操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";
import { AccountActionsView } from "@/components/molecules/AccountActionsView";

const meta = {
  title: "Components/Molecules/AccountActionsView",
  component: AccountActionsView,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { authenticated: true, onLogout: fn() },
} satisfies Meta<typeof AccountActionsView>;
export default meta;
type Story = StoryObj<typeof meta>;
export const User: Story = {};
export const Admin: Story = { args: { admin: true } };
export const Anonymous: Story = { args: { authenticated: false } };
