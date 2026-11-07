/** @file HomePage.stories.tsx @description トップページの導線とResponsive表示。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { HomePage } from "@/features/home/components/pages/HomePage";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const meta = {
  title: "Pages/Home/HomePage",
  component: HomePage,
  parameters: { layout: "padded" },
} satisfies Meta<typeof HomePage>;
export default meta;
type Story = StoryObj<typeof meta>;

const assertHomeContent = async (canvasElement: HTMLElement) => {
  const canvas = within(canvasElement);
  await expect(canvas.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  await expect(
    canvas.getByRole("heading", {
      level: 1,
      name: "面接は、練習で、もっと話しやすくなる。",
    }),
  ).toBeInTheDocument();

  await expect(
    canvas.getByRole("link", { name: "今すぐ面接練習を始める" }),
  ).toHaveAttribute("href", "/practice/");
  await expect(
    canvas.getByRole("link", { name: /まずは使い方ガイド/ }),
  ).toHaveAttribute("href", "#home-how-it-works");

  for (const [title, target] of [
    ["カテゴリから選ぶ", "/practice/category/"],
    ["3分から始める", "/practice/quick/"],
  ]) {
    await expect(
      canvas.getByRole("link", { name: new RegExp(title) }),
    ).toHaveAttribute("href", target);
  }

  await expect(
    canvas.getByRole("heading", {
      level: 2,
      name: "練習を続ける3つのステップ",
    }),
  ).toBeInTheDocument();
  const steps = within(canvas.getByRole("list")).getAllByRole("listitem");
  await expect(steps).toHaveLength(3);
  for (const [index, text] of [
    "質問を選ぶ",
    "自分の言葉で答える",
    "フィードバックで振り返る",
  ].entries()) {
    await expect(steps[index]).toHaveTextContent(text);
  }
};

export const Default: Story = {
  play: ({ canvasElement }) => assertHomeContent(canvasElement),
};

export const Mobile: Story = {
  globals: { viewport: { value: "iphoneSe" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};

export const Tablet: Story = {
  globals: { viewport: { value: "ipad" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};

export const LongTextZoom: Story = {
  decorators: [
    (Story) => (
      <div style={{ fontSize: "200%" }}>
        <Story />
      </div>
    ),
  ],
};

export const KeyboardNavigation: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    await userEvent.tab();
    await expect(
      canvas.getByRole("link", { name: "今すぐ面接練習を始める" }),
    ).toHaveFocus();
    await expect(
      canvas.getByRole("link", { name: "今すぐ面接練習を始める" }),
    ).toHaveAttribute("href", "/practice/");
  },
};

export const NoHorizontalOverflow: Story = {
  globals: { viewport: { value: "iphoneSe" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};
