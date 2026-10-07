/** @file AuthBoundaryView.stories.tsx @description Components/Organisms/AuthBoundaryViewの状態と操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AuthBoundaryView } from "@/components/organisms/AuthBoundaryView";

const meta = {
  title: "Components/Organisms/AuthBoundaryView",
  component: AuthBoundaryView,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: {
    children: "ログイン済みの画面",
    loginUrl: "/login/?returnTo=%2Fpractice%2F",
    status: "allowed",
  },
} satisfies Meta<typeof AuthBoundaryView>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Authenticated: Story = {};
export const Restoring: Story = { args: { status: "restoring" } };
export const Anonymous: Story = { args: { status: "anonymous" } };
export const Forbidden: Story = { args: { status: "forbidden" } };
export const Expired: Story = {
  args: {
    status: "anonymous",
    error: "ログインし直してください。編集内容は保持しています。",
  },
};
export const Refreshing: Story = {};
