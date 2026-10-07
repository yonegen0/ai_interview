/** @file CoachingFeedbackCard.stories.tsx @description V2 scores, statuses, Unicode, and plain-text rendering. */
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, within } from "storybook/test";
import { FeedbackCard } from "@/features/feedback/components/organisms/FeedbackCard";
import { feedbackV2Schema } from "@/lib/api/schemas";
import { scoreValues } from "@/lib/textLimits";
import { createQuestionFixture, storyIds, storyNow } from "../../../fixtures";
const answer = "顧客を支援したいです。";
const feedback = feedbackV2Schema.parse({
  feedbackVersion: 2,
  attemptId: storyIds.currentAttempt,
  evaluationId: storyIds.evaluation,
  sessionId: storyIds.session,
  question: createQuestionFixture(),
  questionNumber: 1,
  answer,
  latestAnswer: answer,
  coachingHistory: [],
  coachingCount: 0,
  result: {
    status: "completed",
    conclusion_score: 8,
    specificity_score: 8,
    reasoning_score: 8,
    good_point: "考えが明確です。",
    improvement: "具体例を確認しましょう。",
    follow_up_question: null,
    example: answer,
  },
  ...scoreValues(answer, 8, 8, 8),
  createdAt: storyNow,
});
const meta = {
  title: "Components/Organisms/Feedback/CoachingFeedbackCard",
  component: FeedbackCard,
  args: { feedback },
  parameters: { layout: "padded" },
} satisfies Meta<typeof FeedbackCard>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Completed: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByText("/ 30 · A")).toBeInTheDocument();
    await expect(
      canvas.getByRole("heading", { name: "改善回答" }),
    ).toBeInTheDocument();
  },
};
export const Coaching: Story = {
  args: {
    feedback: feedbackV2Schema.parse({
      ...feedback,
      result: {
        ...feedback.result,
        status: "coaching",
        follow_up_question: "本人の行動を教えてください。",
        example: null,
      },
    }),
  },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).queryByRole("heading", { name: "改善回答" }),
    ).not.toBeInTheDocument();
  },
};
export const LowScoreCompleted: Story = {
  args: {
    feedback: feedbackV2Schema.parse({
      ...feedback,
      result: {
        ...feedback.result,
        conclusion_score: 5,
        specificity_score: 5,
        reasoning_score: 4,
      },
      ...scoreValues(answer, 5, 5, 4),
    }),
  },
};
export const Emoji400: Story = {
  args: {
    feedback: feedbackV2Schema.parse({
      ...feedback,
      answer: "🙂".repeat(400),
      latestAnswer: "🙂".repeat(400),
      ...scoreValues("🙂".repeat(400), 8, 8, 8),
    }),
  },
};
export const HtmlIsText: Story = {
  args: {
    feedback: feedbackV2Schema.parse({
      ...feedback,
      answer: '<script>alert("x")</script>',
      latestAnswer: '<script>alert("x")</script>',
      ...scoreValues('<script>alert("x")</script>', 8, 8, 8),
    }),
  },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).getByText('<script>alert("x")</script>'),
    ).toBeInTheDocument();
    await expect(canvasElement.querySelector("script")).toBeNull();
  },
};
