/** @file ErrorView.stories.tsx @description APIエラー種別ごとの利用者向け案内。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { ErrorView } from "@/components/organisms/ErrorView";
import { ApiError } from "@/lib/api/client";
import { storyTexts } from "../../fixtures";
import { withAppShell } from "../../test-utils/withAppShell";

const retry = fn();
const meta = {
  title: "Components/Organisms/ErrorView",
  component: ErrorView,
  parameters: { layout: "padded" },
  args: { error: new ApiError("NETWORK_ERROR"), retry },
} satisfies Meta<typeof ErrorView>;
export default meta;
type Story = StoryObj<typeof meta>;
export const ValidationError: Story = {
  args: { error: new ApiError("VALIDATION_ERROR"), retry: undefined },
};
export const Unauthorized: Story = {
  args: { error: new ApiError("UNAUTHORIZED", 401), retry: undefined },
};
export const NotFound: Story = {
  args: { error: new ApiError("SESSION_NOT_FOUND", 404), retry: undefined },
};
export const NetworkError: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getAllByRole("alert")).toHaveLength(1);
    await expect(canvas.getByRole("alert")).toHaveTextContent(
      args.error.message,
    );
    await expect(canvas.getByRole("alert").querySelector("button")).toBeNull();
    await expect(
      canvas.getByRole("heading", { name: "確認が必要です" }),
    ).toBeVisible();
  },
};
export const Timeout: Story = { args: { error: new ApiError("TIMEOUT") } };
export const ServerError: Story = {
  args: { error: new ApiError("INTERNAL_SERVER_ERROR", 500) },
};
export const InvalidResponse: Story = {
  args: { error: new ApiError("INVALID_RESPONSE") },
};
export const LongMessage: Story = {
  args: { error: new Error(storyTexts.text500) },
};
export const Mobile: Story = { globals: { viewport: { value: "iphoneSe" } } };
export const RetryInteraction: Story = {
  play: async ({ canvasElement }) => {
    const button = within(canvasElement).getByRole("button", {
      name: "もう一度確認する",
    });
    await userEvent.click(button);
    await expect(retry).toHaveBeenCalledOnce();
  },
};
export const InAppShell: Story = {
  decorators: [withAppShell],
  parameters: { layout: "fullscreen" },
};
export const LongMessageInAppShell: Story = {
  ...LongMessage,
  decorators: [withAppShell],
  parameters: { layout: "fullscreen" },
};
