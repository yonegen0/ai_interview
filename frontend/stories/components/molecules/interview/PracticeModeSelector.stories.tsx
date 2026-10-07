/** @file PracticeModeSelector.stories.tsx @description Components/Molecules/Interview/PracticeModeSelectorの表示・操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";
import { PracticeModeSelector } from "@/features/interview/components/molecules/PracticeModeSelector";

const meta = {
  title: "Components/Molecules/Interview/PracticeModeSelector",
  component: PracticeModeSelector,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { mode: "full", total: 15, disabled: false, onSelect: fn() },
} satisfies Meta<typeof PracticeModeSelector>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Full: Story = {};
export const Category: Story = { args: { mode: "category" } };
export const Disabled: Story = { args: { disabled: true } };
