/** @file MascotCoachCard.stories.tsx @description 案内カードの配色・構成・長文・画像失敗を検証する。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import {
  expect,
  fireEvent,
  fn,
  userEvent,
  waitFor,
  within,
} from "storybook/test";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { Button } from "@/components/atoms/Button";
import { Link } from "@/components/atoms/Link";
import { storyTexts } from "../../fixtures";

const retry = fn();
const meta = {
  title: "Components/Molecules/MascotCoachCard",
  component: MascotCoachCard,
  parameters: { layout: "padded" },
  args: {
    variant: "thinking",
    heading: <h2>回答を確認しています</h2>,
    children: <p>あなたの回答をもとにフィードバックを作成しています。</p>,
    actions: <Button onClick={retry}>結果を再確認</Button>,
  },
} satisfies Meta<typeof MascotCoachCard>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Standard: Story = {};
export const Featured: Story = {
  args: {
    variant: "success",
    emphasis: "featured",
    heading: (
      <>
        <h1>今回のフィードバック</h1>
        <p>総合評価：78 / 100</p>
      </>
    ),
    children: <p>結論と具体例をつなげる伝え方を確認しましょう。</p>,
    actions: undefined,
  },
};
export const Attention: Story = {
  args: {
    variant: "error",
    tone: "attention",
    heading: <h2>確認が必要です</h2>,
    children: <p>通信状況を確認して、もう一度お試しください。</p>,
    actions: (
      <>
        <Button onClick={retry}>もう一度確認する</Button>
        <Link href="/practice/">練習を始める画面へ</Link>
      </>
    ),
  },
};
export const Error: Story = {
  args: { ...Attention.args, tone: "error" },
};
export const LongContent: Story = {
  args: { children: <p>{storyTexts.text500}</p> },
};
export const WithoutActions: Story = { args: { actions: undefined } };
export const HeadingOnly: Story = {
  args: { children: undefined, actions: undefined },
  play: async ({ canvasElement }) => {
    const card =
      within(canvasElement).getByRole("heading").parentElement!.parentElement!;
    await expect(card.children).toHaveLength(2);
    await expect(canvasElement.querySelector("button")).toBeNull();
  },
};
export const Mobile: Story = {
  ...Attention,
  globals: { viewport: { value: "iphoneSe" } },
  play: async ({ canvasElement }) => {
    const image = canvasElement.querySelector("img")!;
    const paragraph = within(canvasElement).getByText(
      "通信状況を確認して、もう一度お試しください。",
    );
    const body = paragraph.getBoundingClientRect();
    const artwork = image.getBoundingClientRect();
    await expect(body.top).toBeGreaterThanOrEqual(artwork.bottom);
    await expect(body.right).toBeGreaterThanOrEqual(artwork.right - 1);
    await expect(body.left).toBeLessThan(artwork.left);
  },
};
export const ImageLoadFailure: Story = {
  play: async ({ canvasElement }) => {
    const image = canvasElement.querySelector("img")!;
    await waitFor(() => expect(image.naturalWidth).toBeGreaterThan(0));
    const frame = image.parentElement!;
    const before = frame.getBoundingClientRect();
    fireEvent.error(image);
    await expect(image).not.toBeVisible();
    expect(frame.getBoundingClientRect().width).toBe(before.width);
    expect(frame.getBoundingClientRect().height).toBe(before.height);
    const canvas = within(canvasElement);
    await expect(
      canvas.getByRole("heading", { name: "回答を確認しています" }),
    ).toBeVisible();
    await userEvent.click(canvas.getByRole("button", { name: "結果を再確認" }));
    await expect(retry).toHaveBeenCalledOnce();
  },
};
