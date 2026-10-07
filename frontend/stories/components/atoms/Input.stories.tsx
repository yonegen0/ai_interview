/** @file Input.stories.tsx @description 面接回答で使うInputの代表状態。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { loginSchema } from "@/features/auth/model/login";
import { Button } from "@/components/atoms/Button";
import { styled } from "@mui/material/styles";
import { Input } from "@/components/atoms/Input";
import { useState } from "react";
import { theme } from "@/theme/theme";
import { storyTexts } from "../../fixtures";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const StoryFrame = styled("div")({ width: "min(100%, 520px)" });
const meta = {
  title: "Components/Atoms/Input",
  component: Input,
  parameters: { layout: "padded" },
  decorators: [
    (Story) => (
      <StoryFrame>
        <Story />
      </StoryFrame>
    ),
  ],
  args: { label: "あなたの回答", placeholder: "回答を入力してください" },
} satisfies Meta<typeof Input>;
export default meta;
type Story = StoryObj;

export const Default: Story = {};
export const WithLabel: Story = { args: { label: "メールアドレス" } };
export const WithHelperText: Story = {
  args: { helperText: "100〜300文字がおすすめです" },
};
export const ErrorState: Story = {
  args: { error: true, helperText: "空白以外の回答を入力してください" },
};
export const Disabled: Story = {
  args: { disabled: true, defaultValue: "送信中の回答です" },
};
export const Multiline: Story = { args: { multiline: true, minRows: 6 } };
export const LongText: Story = {
  args: { multiline: true, defaultValue: storyTexts.text1000 },
};
export const KeyboardFocus: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.tab();
    await expect(
      within(canvasElement).getByLabelText("あなたの回答"),
    ).toHaveFocus();
  },
};
export const Mobile: Story = {
  args: { multiline: true, defaultValue: storyTexts.text500 },
  globals: { viewport: { value: "iphoneSe" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};

export const Email: Story = {
  args: { label: "メールアドレス", type: "email", autoComplete: "email" },
};
export const Otp: Story = {
  args: {
    label: "確認コード",
    autoComplete: "one-time-code",
    slotProps: { htmlInput: { inputMode: "numeric" } },
  },
};
export const QuestionBody: Story = {
  args: {
    label: "質問本文",
    multiline: true,
    minRows: 4,
    defaultValue: "一文目です。\n二文目です。",
  },
};
function RhfInputHarness() {
  const form = useForm({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", code: "" },
  });
  return (
    <form onSubmit={form.handleSubmit(() => {})} noValidate>
      <Controller
        control={form.control}
        name="email"
        render={({ field: { ref, ...field } }) => (
          <Input
            {...field}
            inputRef={ref}
            label="メールアドレス"
            error={!!form.formState.errors.email}
            helperText={form.formState.errors.email?.message}
          />
        )}
      />
      <Button type="submit">入力を確認</Button>
    </form>
  );
}
export const RhfValidationFocus: Story = {
  render: () => <RhfInputHarness />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "入力を確認" }));
    await expect(
      await canvas.findByText("メールアドレスを確認してください。"),
    ).toBeVisible();
    await expect(canvas.getByLabelText("メールアドレス")).toHaveFocus();
  },
};

function ErrorRecoveryInput() {
  const [value, setValue] = useState("");
  return (
    <Input
      label="修正する入力"
      value={value}
      onChange={(event) => setValue(event.target.value)}
      error={!value.trim()}
      helperText={!value.trim() ? "入力してください。" : "入力を確認しました。"}
    />
  );
}
export const ErrorFocusHoverAndRecovery: Story = {
  render: () => <ErrorRecoveryInput />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = canvas.getByLabelText("修正する入力");
    const root = input.closest(".MuiFormControl-root")!;
    const label = root.querySelector("label")!;
    const outline = root.querySelector("fieldset")!;
    await userEvent.click(input);
    await userEvent.hover(input);
    await expect(label).toHaveStyle({ color: theme.palette.error.main });
    await expect(outline).toHaveStyle({
      borderColor: theme.palette.error.main,
    });
    await waitFor(() =>
      expect(
        getComputedStyle(input.closest(".MuiOutlinedInput-root")!).boxShadow,
      ).toContain("179, 38, 30"),
    );
    await userEvent.type(input, "修正済み");
    await expect(canvas.getByText("入力を確認しました。")).toBeVisible();
    await waitFor(() =>
      expect(label).toHaveStyle({ color: theme.palette.primary.main }),
    );
    await waitFor(() =>
      expect(outline).toHaveStyle({ borderColor: theme.palette.primary.main }),
    );
    await expect(input).toHaveAttribute("aria-invalid", "false");
  },
};
export const DisabledErrorPriority: Story = {
  args: { error: true, disabled: true, helperText: "入力できません。" },
  play: async ({ canvasElement }) => {
    const input = within(canvasElement).getByLabelText("あなたの回答");
    await expect(input).toBeDisabled();
    await expect(
      input.closest(".MuiFormControl-root")!.querySelector("label"),
    ).toHaveStyle({ color: theme.palette.text.disabled });
    await expect(input.closest(".MuiOutlinedInput-root")).toHaveStyle({
      boxShadow: "none",
    });
  },
};
