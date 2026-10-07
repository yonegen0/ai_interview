/** @file Select.stories.tsx @description 面接カテゴリSelectの代表状態。 */
import { useForm, Controller } from "react-hook-form";
import { Button } from "@/components/atoms/Button";
import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";
import { Select } from "@/components/atoms/Select";
import { theme } from "@/theme/theme";
import { categories, type Category } from "@/lib/api/schemas";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const options = Object.entries(categories).map(([value, label]) => ({
  value: value as Category,
  label,
}));
const SelectHarness = (props: {
  initial?: Category;
  disabled?: boolean;
  error?: string;
  size?: "small" | "medium";
}) => {
  const [value, setValue] = useState<Category>(props.initial ?? "job_change");
  return (
    <Select
      label="面接カテゴリ"
      value={value}
      onChange={setValue}
      options={options}
      fullWidth
      disabled={props.disabled}
      error={props.error}
      size={props.size}
    />
  );
};
const meta = {
  title: "Components/Atoms/Select",
  component: Select,
  parameters: { layout: "padded" },
} satisfies Meta<typeof Select>;
export default meta;
type Story = StoryObj;

export const Default: Story = { render: () => <SelectHarness /> };
export const Selected: Story = {
  render: () => <SelectHarness initial="motivation" />,
};
export const FullWidth: Story = { render: () => <SelectHarness /> };
export const Small: Story = { render: () => <SelectHarness size="small" /> };
export const WithError: Story = {
  render: () => <SelectHarness error="カテゴリを選択してください" />,
};
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

function RhfSelectHarness() {
  const form = useForm<{ category: string }>({
    defaultValues: { category: "" },
  });
  return (
    <form onSubmit={form.handleSubmit(() => {})}>
      <span id="category-instructions">カテゴリを選択してください。</span>
      <Controller
        control={form.control}
        name="category"
        rules={{ required: "カテゴリは必須です。" }}
        render={({ field: { ref, ...field } }) => (
          <Select
            {...field}
            inputRef={ref}
            id="rhf-category"
            describedBy="category-instructions"
            label="カテゴリ"
            options={[
              { value: "career", label: "キャリア" },
              { value: "strengths", label: "強み" },
            ]}
            error={form.formState.errors.category?.message}
          />
        )}
      />
      <Button type="submit">入力を確認</Button>
    </form>
  );
}
export const RhfValidationAndSelection: Story = {
  render: () => <RhfSelectHarness />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "入力を確認" }));
    await expect(await canvas.findByText("カテゴリは必須です。")).toBeVisible();
    const select = canvas.getByRole("combobox", { name: "カテゴリ" });
    await expect(select).toHaveFocus();
    await expect(select).toHaveAccessibleDescription(
      /カテゴリを選択してください/,
    );
    await userEvent.keyboard("{Enter}");
    await userEvent.click(
      await within(document.body).findByRole("option", { name: "強み" }),
    );
    await expect(select).toHaveTextContent("強み");
  },
};

function ErrorRecoverySelect() {
  const [value, setValue] = useState("");
  return (
    <Select
      label="修正するカテゴリ"
      value={value}
      onChange={setValue}
      options={[{ value: "career", label: "キャリア" }]}
      fullWidth
      error={value ? undefined : "カテゴリを選択してください。"}
    />
  );
}
export const ErrorFocusHoverAndRecovery: Story = {
  render: () => <ErrorRecoverySelect />,
  play: async ({ canvasElement }) => {
    const select = within(canvasElement).getByRole("combobox");
    const root = select.closest(".MuiFormControl-root")!;
    await userEvent.tab();
    await expect(select).toHaveFocus();
    await userEvent.hover(select);
    await expect(root.querySelector("label")).toHaveStyle({
      color: theme.palette.error.main,
    });
    await expect(root.querySelector("fieldset")).toHaveStyle({
      borderColor: theme.palette.error.main,
    });
    await userEvent.keyboard("{Enter}");
    await userEvent.click(
      await within(document.body).findByRole("option", { name: "キャリア" }),
    );
    await expect(select).toHaveTextContent("キャリア");
    await waitFor(() =>
      expect(root.querySelector("label")).toHaveStyle({
        color: theme.palette.primary.main,
      }),
    );
    await waitFor(() =>
      expect(root.querySelector("fieldset")).toHaveStyle({
        borderColor: theme.palette.primary.main,
      }),
    );
  },
};
export const DisabledErrorPriority: Story = {
  render: () => <SelectHarness disabled error="入力できません。" />,
  play: async ({ canvasElement }) => {
    const select = within(canvasElement).getByRole("combobox");
    const root = select.closest(".MuiFormControl-root")!;
    await expect(select).toHaveAttribute("aria-disabled", "true");
    await expect(root.querySelector("label")).toHaveStyle({
      color: theme.palette.text.disabled,
    });
    await expect(select.closest(".MuiOutlinedInput-root")).toHaveStyle({
      boxShadow: "none",
    });
  },
};
