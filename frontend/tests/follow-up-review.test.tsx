/** @file follow-up-review.test.tsx @description 独立採点の契約・旧データと表示を検証。 */
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { expect, it } from "vitest";
import { FeedbackCard } from "@/features/feedback/components/organisms/FeedbackCard";
import {
  feedbackWithReviewsSchema, followUpReviewSchema, feedbackV2Schema,
} from "@/lib/api/schemas";
import { scoreValues } from "@/lib/textLimits";
import { theme } from "@/theme/theme";
import { createQuestionFixture, storyIds, storyNow } from "../stories/fixtures";

const question = "そのとき何をしましたか？";
const answer = "集荷先で他社の送り状を見つけ、利用状況を尋ねました。";
const initial = "お客様の要望を聞きました。";
const feedback = feedbackV2Schema.parse({
  feedbackVersion: 2,
  attemptId: storyIds.currentAttempt,
  evaluationId: storyIds.evaluation,
  sessionId: storyIds.session,
  question: createQuestionFixture(),
  questionNumber: 1,
  answer: initial,
  latestAnswer: answer,
  coachingHistory: [{ question, answer }],
  coachingCount: 1,
  result: {
    status: "completed",
    conclusion_score: 8,
    specificity_score: 8,
    reasoning_score: 8,
    good_point: "本人の行動が明確です。",
    improvement: "再現性を確認しましょう。",
    follow_up_question: null,
    example: initial,
  },
  ...scoreValues(initial, 8, 8, 8),
  createdAt: storyNow,
});
const review = {
  question_fit_score: 9,
  detail_score: 8,
  coherence_score: 9,
  suitability: "ready" as const,
  good_point: "顧客への質問内容を示しています。",
  improvement: "現時点で重要な改善点はありません。",
  totalScore: 26,
};
const item = {
  roundIndex: 1,
  evaluationId: feedback.evaluationId,
  question,
  answer,
  review,
};

it("validates exact review scores and preserves independent aggregate", () => {
  const parsed = feedbackWithReviewsSchema.parse({ feedback, followUpReviews: [item] });
  expect(parsed.followUpReviews[0].review?.totalScore).toBe(26);
  expect(parsed.feedback.totalScore).toBe(feedback.totalScore);
  expect(followUpReviewSchema.safeParse({ ...review, totalScore: 28 }).success).toBe(false);
  expect(followUpReviewSchema.safeParse({ ...review, question_fit_score: 11 }).success).toBe(false);
  expect(followUpReviewSchema.safeParse({ ...review, suitability: "unknown" }).success).toBe(false);
  expect(feedbackWithReviewsSchema.safeParse({
    feedback,
    followUpReviews: [{ ...item, question: "別の質問" }],
  }).success).toBe(false);
});

it("shows separate current and historical reviews without hiding original overall score", () => {
  render(<ThemeProvider theme={theme}><FeedbackCard feedback={feedback} followUpReviews={[item]} /></ThemeProvider>);
  expect(screen.getByRole("heading", { name: "今回の深掘り回答評価" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "総合評価" })).toBeInTheDocument();
  expect(screen.getByText("26 / 30点")).toBeInTheDocument();
  expect(screen.getByText("そのまま使える")).toBeInTheDocument();
  expect(screen.getByText("質問適合性：9 / 10点")).toBeInTheDocument();
  expect(screen.getByText("具体性・情報の充実度：8 / 10点")).toBeInTheDocument();
  expect(screen.getByText("一貫性・納得感：9 / 10点")).toBeInTheDocument();
});

it("keeps old feedback and rounds visible with missing dedicated review", () => {
  render(<ThemeProvider theme={theme}><FeedbackCard feedback={feedback} /></ThemeProvider>);
  expect(screen.getByText("専用評価データなし")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "総合評価" })).toBeInTheDocument();
  expect(screen.getByText(initial)).toBeInTheDocument();
  expect(feedbackWithReviewsSchema.parse({
    feedback, followUpReviews: [{ ...item, review: null }],
  }).followUpReviews[0].review).toBeNull();
});
