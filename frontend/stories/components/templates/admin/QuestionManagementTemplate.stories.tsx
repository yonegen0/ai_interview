/** @file QuestionManagementTemplate.stories.tsx @description Components/Templates/Admin/QuestionManagementTemplateの表示・フォーム状態。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AdminPresentation } from "../../../test-utils/presentation";
const meta = {
  title: "Components/Templates/Admin/QuestionManagementTemplate",
  component: AdminPresentation,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { kind: "template" },
} satisfies Meta<typeof AdminPresentation>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {};
export const Confirmation: Story = { args: { stage: "confirm" } };
export const Uncertain: Story = { args: { stage: "uncertain" } };
export const Conflict: Story = { args: { stage: "conflict" } };
export const Preview: Story = { args: { preview: true } };
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
export const Tablet: Story = { globals: { viewport: { value: "ipad" } } };
export const Desktop: Story = { globals: { viewport: { value: "desktop" } } };
