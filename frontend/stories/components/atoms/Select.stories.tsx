/** @file Select.stories.tsx @description 面接カテゴリSelectの代表状態。 */
import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { Select } from "@/components/atoms/Select";
import { categories, type Category } from "@/lib/api/schemas";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const options = Object.entries(categories).map(([value, label]) => ({ value: value as Category, label }));
const SelectHarness = (props: { initial?: Category; disabled?: boolean; error?: string; size?: "small" | "medium" }) => {
  const [value, setValue] = useState<Category>(props.initial ?? "job_change");
  return <Select label="面接カテゴリ" value={value} onChange={setValue} options={options} fullWidth disabled={props.disabled} error={props.error} size={props.size} />;
};
const meta = { title: "Components/Atoms/Select", component: Select, parameters: { layout: "padded" } } satisfies Meta<typeof Select>;
export default meta;
type Story = StoryObj;

export const Default: Story = { render: () => <SelectHarness /> };
export const Selected: Story = { render: () => <SelectHarness initial="motivation" /> };
export const FullWidth: Story = { render: () => <SelectHarness /> };
export const Small: Story = { render: () => <SelectHarness size="small" /> };
export const WithError: Story = { render: () => <SelectHarness error="カテゴリを選択してください" /> };
export const Disabled: Story = { render: () => <SelectHarness disabled /> };
export const KeyboardSelection: Story = {
  render: () => <SelectHarness />,
  play: async ({ canvasElement }) => {
    await userEvent.tab();
    await userEvent.keyboard("{Enter}{ArrowDown}{Enter}");
    await expect(within(canvasElement).getByRole("combobox")).toHaveFocus();
  },
};
export const Mobile: Story = {
  render: () => <SelectHarness />,
  globals: { viewport: { value: "iphoneSe" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};
