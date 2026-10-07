/** @file PracticeCategorySelector.stories.tsx @description Components/Molecules/Interview/PracticeCategorySelectorの表示・操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";
import { PracticeCategorySelector } from "@/features/interview/components/molecules/PracticeCategorySelector";
import { practiceOptions } from "../../../fixtures/refactor";
const meta = {
  title: "Components/Molecules/Interview/PracticeCategorySelector",
  component: PracticeCategorySelector,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: {
    categories: practiceOptions.categories,
    selected: null,
    disabled: false,
    onSelect: fn(),
  },
} satisfies Meta<typeof PracticeCategorySelector>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Unselected: Story = {};
export const Selected: Story = { args: { selected: "company_selection" } };
export const Empty: Story = { args: { categories: [] } };
export const Disabled: Story = { args: { disabled: true } };
