/** @file FeedbackCard.stories.tsx @description Score、空配列、長文、HTML安全性の表示確認。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, within } from "storybook/test";
import { FeedbackCard } from "@/features/feedback/components/organisms/FeedbackCard";
import { createFeedbackFixture, storyTexts } from "../../fixtures";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const feedback = createFeedbackFixture();
const meta = {
  title: "Components/Organisms/FeedbackCard",
  component: FeedbackCard,
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "スコア、総評、回答内容、改善点を順に読み進められるレポート型のフィードバックカード。",
      },
    },
  },
  args: { feedback },
} satisfies Meta<typeof FeedbackCard>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByRole("heading", {
        level: 1,
        name: "今回のフィードバック",
      }),
    ).toBeInTheDocument();
    await expect(
      canvas.getByRole("heading", { level: 2, name: "総合評価" }),
    ).toBeInTheDocument();
    await expect(canvas.getByText(String(feedback.score))).toBeInTheDocument();
    await expect(canvas.getByText(feedback.summary)).toBeInTheDocument();
  },
};
export const PerfectScore: Story = {
  args: { feedback: createFeedbackFixture({ score: 100 }) },
};
export const ZeroScore: Story = {
  args: { feedback: createFeedbackFixture({ score: 0 }) },
};
export const HighScore: Story = {
  args: { feedback: createFeedbackFixture({ score: 95 }) },
};
export const LowScore: Story = {
  args: { feedback: createFeedbackFixture({ score: 20 }) },
};
export const NoStrengths: Story = {
  args: { feedback: createFeedbackFixture({ strengths: [] }) },
};
export const NoImprovements: Story = {
  args: { feedback: createFeedbackFixture({ improvements: [] }) },
};
export const NoPoints: Story = {
  args: {
    feedback: createFeedbackFixture({ strengths: [], improvements: [] }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getAllByText("該当する項目はありません")).toHaveLength(
      2,
    );
    await expect(canvas.queryByRole("list")).not.toBeInTheDocument();
  },
};
export const FivePoints: Story = {
  args: {
    feedback: createFeedbackFixture({
      strengths: Array(5).fill("結論が明確です。"),
      improvements: Array(5).fill("成果を補足しましょう。"),
    }),
  },
};
export const WithoutExampleAnswer: Story = {
  args: { feedback: createFeedbackFixture({ exampleAnswer: undefined }) },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).queryByRole("heading", { name: "回答例" }),
    ).not.toBeInTheDocument();
  },
};
export const Answer100Characters: Story = {
  args: { feedback: createFeedbackFixture({ answer: storyTexts.text100 }) },
};
export const Answer500Characters: Story = {
  args: { feedback: createFeedbackFixture({ answer: storyTexts.text500 }) },
};
export const Answer1000Characters: Story = {
  args: { feedback: createFeedbackFixture({ answer: storyTexts.text1000 }) },
};
export const Answer2000Characters: Story = {
  args: { feedback: createFeedbackFixture({ answer: storyTexts.text2000 }) },
};
export const MultilineAnswer: Story = {
  args: {
    feedback: createFeedbackFixture({
      answer: "結論です。\n具体例です。\n成果です。",
    }),
  },
};
export const LongGeneratedText: Story = {
  args: {
    feedback: createFeedbackFixture({
      summary: storyTexts.text500,
      strengths: [storyTexts.text500],
      improvements: [storyTexts.text500],
      exampleAnswer: storyTexts.text1000,
    }),
  },
};
export const UnsafeHtmlText: Story = {
  args: {
    feedback: createFeedbackFixture({
      answer: "<script>window.storyExecuted=true</script>",
    }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByText("<script>window.storyExecuted=true</script>"),
    ).toBeInTheDocument();
    await expect(canvasElement.querySelector("script")).toBeNull();
    await expect(
      (window as Window & { storyExecuted?: boolean }).storyExecuted,
    ).toBeUndefined();
  },
};
export const Mobile: Story = {
  ...Answer1000Characters,
  globals: { viewport: { value: "iphoneSe" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};
export const Tablet: Story = {
  globals: { viewport: { value: "ipad" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};
export const Desktop: Story = {
  globals: { viewport: { value: "desktop" } },
  play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement),
};
