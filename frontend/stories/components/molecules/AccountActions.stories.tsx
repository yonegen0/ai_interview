/** @file AccountActions.stories.tsx @description Components/Molecules/AccountActionsの表示・操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AccountActions } from "@/components/molecules/AccountActions";

const meta = {
  title: "Components/Molecules/AccountActions",
  component: AccountActions,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: {},
} satisfies Meta<typeof AccountActions>;
export default meta;
type Story = StoryObj<typeof meta>;
export const User: Story = {};
export const Admin: Story = { parameters: { mockRole: "ADMIN" } };
export const Anonymous: Story = { parameters: { mockRole: "ANONYMOUS" } };
