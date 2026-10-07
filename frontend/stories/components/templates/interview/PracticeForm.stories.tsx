/** @file PracticeForm.stories.tsx @description Components/Templates/Interview/PracticeFormの表示・フォーム状態。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AnswerPresentation } from "../../../test-utils/presentation";
import { expect, userEvent, waitFor, within } from "storybook/test";
import { theme } from "@/theme/theme";
const meta = {
  title: "Components/Templates/Interview/PracticeForm",
  component: AnswerPresentation,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  args: { template: true },
} satisfies Meta<typeof AnswerPresentation>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Answering: Story = {};
export const Processing: Story = { args: { phase: "processing" } };
export const Failed: Story = { args: { phase: "failed" } };
export const ExitConfirmation: Story = {
  args: { confirm: true, text: "下書きです。" },
};
export const LegacyProgress: Story = { args: { legacy: true } };
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
export const Tablet: Story = { globals: { viewport: { value: "ipad" } } };
export const Desktop: Story = { globals: { viewport: { value: "desktop" } } };

export const ExitWhileSubmitting: Story = {
  args: { confirm: true, phase: "submitting", text: "送信中の回答" },
  play: async () => {
    const dialog = within(within(document.body).getByRole("dialog"));
    await waitFor(() =>
      expect(dialog.getByText(/送信内容を保持して終了します/)).toBeVisible(),
    );
    await waitFor(() =>
      expect(
        dialog.getByRole("link", { name: "未確定の送信を保持して終了" }),
      ).toBeVisible(),
    );
  },
};
export const ExitWithUncertainRequest: Story = {
  args: { confirm: true, phase: "recovery_required", text: "結果不明の回答" },
  play: async () => {
    const dialog = within(within(document.body).getByRole("dialog"));
    await waitFor(() =>
      expect(dialog.getByText(/元の練習で結果を再確認できます/)).toBeVisible(),
    );
    await waitFor(() =>
      expect(
        dialog.getByRole("link", { name: "未確定の送信を保持して終了" }),
      ).toBeVisible(),
    );
  },
};
export const ExitWhileProcessing: Story = {
  args: { confirm: true, phase: "processing" },
  play: async () => {
    await waitFor(() =>
      expect(
        within(document.body).getByText("送信済みの評価は中止されません。"),
      ).toBeVisible(),
    );
  },
};
export const ExitAfterCompletion: Story = {
  args: { confirm: true, phase: "completed" },
  play: async () => {
    await waitFor(() =>
      expect(
        within(document.body).getByText("送信済みの評価は中止されません。"),
      ).toBeVisible(),
    );
  },
};
export const ExitAfterFailure: Story = {
  args: { confirm: true, phase: "failed" },
  play: async () => {
    await waitFor(() =>
      expect(
        within(document.body).getByText("練習画面を離れます。"),
      ).toBeVisible(),
    );
  },
};
export const PortalKeyboardFocus: Story = {
  args: { confirm: true, text: "下書きです。" },
  play: async () => {
    const button = within(document.body).getByRole("button", {
      name: "続ける",
    });
    await expect(button).toHaveFocus();
    await userEvent.tab();
    await userEvent.tab({ shift: true });
    await expect(button).toHaveStyle({
      outlineWidth: "3px",
      outlineColor: theme.palette.primary.main,
    });
  },
};
