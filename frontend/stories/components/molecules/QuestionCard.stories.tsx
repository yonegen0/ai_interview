/** @file QuestionCard.stories.tsx @description 質問カードのカテゴリ、長文、狭幅表示。 */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { QuestionCard } from "@/features/interview/components/molecules/QuestionCard";
import { categories } from "@/lib/api/schemas";
import { questions } from "@/mocks/data/questions";
import { createQuestionFixture, storyTexts } from "../../fixtures";
import { assertNoHorizontalOverflow } from "../../test-utils/storyEnvironment";

const meta = { title: "Components/Molecules/QuestionCard", component: QuestionCard, parameters: { layout: "padded" }, args: { question: createQuestionFixture(), number: 1 } } satisfies Meta<typeof QuestionCard>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {};
export const Question10: Story = { args: { number: 10 } };
export const LongQuestion: Story = { args: { question: createQuestionFixture({ question: storyTexts.text500 }) } };
export const AllCategories: Story = {
  render: () => <div>{Object.keys(categories).map((category) => { const question = questions.find((item) => item.category === category)!; return <QuestionCard key={category} question={question} number={1} />; })}</div>,
};
export const Mobile: Story = { ...LongQuestion, globals: { viewport: { value: "iphoneSe" } } };
export const NoHorizontalOverflow: Story = { ...Mobile, play: ({ canvasElement }) => assertNoHorizontalOverflow(canvasElement) };
