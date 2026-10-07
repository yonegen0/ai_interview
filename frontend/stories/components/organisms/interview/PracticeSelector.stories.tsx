/** @file PracticeSelector.stories.tsx @description Components/Organisms/Interview/PracticeSelectorの表示・操作。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { fn } from "storybook/test";
import { PracticeSelector } from "@/features/interview/components/organisms/PracticeSelector";
import { practiceOptions } from "../../../fixtures/refactor";
import type { PracticeStartView } from "@/features/interview/model/practiceStart";
const view: PracticeStartView = {
  mode: "full",
  category: null,
  options: practiceOptions,
  loading: false,
  optionsError: null,
  error: null,
  disabled: false,
  canStart: true,
  starting: false,
  recovering: false,
};
const meta = {
  title: "Components/Organisms/Interview/PracticeSelector",
  component: PracticeSelector,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: {
    view,
    actions: {
      selectMode: fn(),
      selectCategory: fn(),
      start: fn(async () => {}),
      refresh: fn(),
    },
  },
} satisfies Meta<typeof PracticeSelector>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Full: Story = {};
export const Category: Story = {
  args: { view: { ...view, mode: "category", canStart: false } },
};
export const Selected: Story = {
  args: { view: { ...view, mode: "category", category: "company_selection" } },
};
export const Loading: Story = {
  args: {
    view: { ...view, loading: true, options: undefined, canStart: false },
  },
};
export const FetchFailure: Story = {
  args: {
    view: {
      ...view,
      options: undefined,
      canStart: false,
      optionsError: new Error("取得できませんでした。"),
    },
  },
};
export const Starting: Story = {
  args: { view: { ...view, starting: true, disabled: true, canStart: false } },
};
export const Uncertain: Story = {
  args: { view: { ...view, recovering: true, disabled: true } },
};
