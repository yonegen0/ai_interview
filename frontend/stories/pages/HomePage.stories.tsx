/** @file HomePage.stories.tsx @description トップページの導線とResponsive表示。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { HomePage } from "@/features/home/components/pages/HomePage";
import { assertNoHorizontalOverflow } from "../test-utils/storyEnvironment";

const meta = {
  title: "Pages/Home",
  component: HomePage,
  parameters: { layout: "padded" },
} satisfies Meta<typeof HomePage>;
export default meta;
type Story = StoryObj<typeof meta>;

const assertHomeContent = async (canvasElement: HTMLElement) => {
  const canvas = within(canvasElement);
  const steps = [
    {
      title: "カテゴリを選ぶ",
      description: "練習したいテーマを選んで、一問から始めましょう。",
    },
    {
      title: "自分の言葉で答える",
      description: "質問を読み、経験や考えを文章にまとめましょう。",
    },
    {
      title: "振り返って、もう一度",
      description: "フィードバックを確認して、再挑戦や次の質問へ進みましょう。",
    },
  ];

  await expect(canvas.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  await expect(
    canvas.getByRole("heading", {
      level: 1,
      name: "今日の3分が、面接の自信になる。",
    }),
  ).toBeInTheDocument();
  const stepList = canvas.getByRole("list");
  await expect(within(stepList).getAllByRole("listitem")).toHaveLength(3);

  for (const step of steps) {
    await expect(
      canvas.getByRole("heading", { level: 3, name: step.title }),
    ).toBeInTheDocument();
    await expect(canvas.getByText(step.description)).toBeInTheDocument();
  }

  await expect(
    canvas.getByRole("link", { name: "面接練習を始める →" }),
  ).toHaveAttribute("href", "/practice/");
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
      canvas.getByRole("link", { name: /面接練習を始める/ }),
    ).toHaveFocus();
    await expect(
      canvas.getByRole("link", { name: /面接練習を始める/ }),
    ).toHaveAttribute("href", "/practice/");
  },
};

export const NoHorizontalOverflow: Story = {
  globals: { viewport: { value: "iphoneSe" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};
