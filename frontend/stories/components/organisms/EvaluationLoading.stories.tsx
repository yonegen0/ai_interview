/** @file EvaluationLoading.stories.tsx @description 評価待機、停止、通信エラーの表示。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { EvaluationLoading } from "@/features/interview/components/organisms/EvaluationLoading";
import { ApiError } from "@/lib/api/client";
import { withAppShell } from "../../test-utils/withAppShell";

const retry = fn();
const meta = {
  title: "Components/Organisms/EvaluationLoading",
  component: EvaluationLoading,
  parameters: { layout: "padded" },
  args: { elapsed: 0, paused: false, retry },
} satisfies Meta<typeof EvaluationLoading>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Processing: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole("status")).toBeInTheDocument();
    await expect(canvas.getByLabelText("評価処理中")).toBeInTheDocument();
    await expect(
      canvas.queryByText("%", { exact: false }),
    ).not.toBeInTheDocument();
  },
};
export const LongWait: Story = { args: { elapsed: 30 } };
export const AutoPaused: Story = { args: { elapsed: 120, paused: true } };
export const OfflinePaused: Story = { args: { paused: true } };
export const NetworkError: Story = {
  args: { paused: true, error: new ApiError("NETWORK_ERROR") },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getAllByRole("status")).toHaveLength(1);
    await expect(canvas.queryByLabelText("評価処理中")).toBeNull();
    await expect(
      canvasElement.querySelector('img[src$="mascot-thinking.webp"]'),
    ).toBeVisible();
    await expect(canvas.getByRole("status").querySelector("button")).toBeNull();
    await expect(
      canvas.getByRole("button", { name: "結果を再確認" }),
    ).toBeEnabled();
  },
};
export const Timeout: Story = {
  args: { paused: true, error: new ApiError("TIMEOUT") },
};
export const RetryInteraction: Story = {
  args: { paused: true },
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole("button", { name: "結果を再確認" }),
    );
    await expect(retry).toHaveBeenCalledOnce();
  },
};
export const Mobile: Story = {
  args: { elapsed: 120, paused: true },
  globals: { viewport: { value: "iphoneSe" } },
};
export const InAppShell: Story = {
  decorators: [withAppShell],
  parameters: { layout: "fullscreen" },
};
export const AutoPausedInAppShell: Story = {
  ...AutoPaused,
  decorators: [withAppShell],
  parameters: { layout: "fullscreen" },
};
