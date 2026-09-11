/** @file MascotCharacter.stories.tsx @description マスコットの表情、サイズ、画像取得失敗の表示確認。 */
import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fireEvent, userEvent, waitFor, within } from "storybook/test";
import { MascotCharacter } from "@/components/atoms/MascotCharacter";
import { Actions } from "@/components/atoms/Actions";
import { Button } from "@/components/atoms/Button";

const meta = {
  title: "Components/Atoms/MascotCharacter",
  component: MascotCharacter,
  args: { variant: "default", size: "sm" },
} satisfies Meta<typeof MascotCharacter>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Welcome: Story = { args: { variant: "welcome", size: "lg" } };
export const Thinking: Story = { args: { variant: "thinking", size: "md" } };
export const Success: Story = { args: { variant: "success" } };
export const Retry: Story = { args: { variant: "retry" } };
export const Error: Story = { args: { variant: "error" } };
export const Mobile: Story = {
  ...Welcome,
  globals: { viewport: { value: "iphoneSe" } },
};
export const Sizes: Story = {
  render: () => (
    <Actions>
      <MascotCharacter size="sm" />
      <MascotCharacter size="md" />
      <MascotCharacter size="lg" />
    </Actions>
  ),
};

const FailureExample = () => {
  const [changed, setChanged] = useState(false);
  return (
    <Actions>
      <MascotCharacter variant={changed ? "success" : "welcome"} size="lg" />
      <Button onClick={() => setChanged(true)}>別の表情を表示</Button>
    </Actions>
  );
};

export const ImageLoadFailure: Story = {
  render: () => <FailureExample />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const image = canvasElement.querySelector("img")!;
    await waitFor(() => expect(image.naturalWidth).toBeGreaterThan(0));
    const frame = image.parentElement!;
    const before = frame.getBoundingClientRect();
    fireEvent.error(image);
    await expect(image).not.toBeVisible();
    expect(frame.getBoundingClientRect().width).toBe(before.width);
    expect(frame.getBoundingClientRect().height).toBe(before.height);
    await userEvent.click(
      canvas.getByRole("button", { name: "別の表情を表示" }),
    );
    const replacement = canvasElement.querySelector("img")!;
    await waitFor(() => expect(replacement.naturalWidth).toBeGreaterThan(0));
    await expect(replacement).toBeVisible();
    await expect(replacement).toHaveAttribute(
      "src",
      expect.stringContaining("/images/mascot/mascot-success.webp"),
    );
  },
};
