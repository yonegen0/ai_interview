/** @file AuthBoundary.stories.tsx @description Components/Organisms/AuthBoundaryの表示・操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";

const meta = {
  title: "Components/Organisms/AuthBoundary",
  component: AuthBoundary,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { children: "保護された画面" },
} satisfies Meta<typeof AuthBoundary>;
export default meta;
type Story = StoryObj<typeof meta>;
export const User: Story = {};
export const Admin: Story = {
  args: { admin: true },
  parameters: { mockRole: "ADMIN" },
};
export const Forbidden: Story = { args: { admin: true } };
export const Anonymous: Story = { parameters: { mockRole: "ANONYMOUS" } };
