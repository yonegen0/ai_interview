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
  expect(parsed.feedback).toEqual(feedback);
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
  expect(screen.getByLabelText("26 / 30点")).toBeInTheDocument();
  expect(screen.getAllByText("そのまま使える").length).toBeGreaterThan(0);
  expect(screen.getByRole("group", { name: "質問適合性：9 / 10点" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "具体性・情報の充実度：8 / 10点" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "一貫性・納得感：9 / 10点" })).toBeInTheDocument();
  expect(screen.getByText(review.good_point)).toBeInTheDocument();
  expect(screen.getByText(review.improvement)).toBeInTheDocument();
});

it("keeps old feedback and rounds visible with missing dedicated review", () => {
  render(<ThemeProvider theme={theme}><FeedbackCard feedback={feedback} /></ThemeProvider>);
  expect(screen.getAllByText("専用評価データなし").length).toBeGreaterThan(0);
  expect(screen.getByRole("heading", { name: "総合評価" })).toBeInTheDocument();
  expect(screen.getAllByText(initial).length).toBeGreaterThan(0);
  expect(feedbackWithReviewsSchema.parse({
    feedback, followUpReviews: [{ ...item, review: null }],
  }).followUpReviews[0].review).toBeNull();
});

it.each([
  ["ready", "そのまま使える"],
  ["minor_revision", "概ね適切・微修正"],
  ["needs_revision", "要修正"],
  ["needs_verification", "情報不足・要確認"],
] as const)("keeps the %s suitability label", (suitability, label) => {
  render(
    <ThemeProvider theme={theme}>
      <FeedbackCard feedback={feedback} followUpReviews={[{ ...item, review: { ...review, suitability } }]} />
    </ThemeProvider>
  );
  expect(screen.getByText(label)).toBeInTheDocument();
});

it("shows the latest review without confusing it with other rounds", () => {
  const secondQuestion = "その判断をした理由は？";
  const secondAnswer = "配達先の課題を聞いたためです。";
  const thirdQuestion = "結果をどう確認しましたか？";
  const thirdAnswer = "集荷の利用開始を確認しました。";
  const latestFeedback = feedbackV2Schema.parse({
    ...feedback,
    coachingCount: 3,
    coachingHistory: [
      { question, answer },
      { question: secondQuestion, answer: secondAnswer },
      { question: thirdQuestion, answer: thirdAnswer },
    ],
    latestAnswer: thirdAnswer,
  });
  const reviews = [
    item,
    {
      roundIndex: 2,
      evaluationId: feedback.evaluationId,
      question: secondQuestion,
      answer: secondAnswer,
      review: { ...review, totalScore: 24, question_fit_score: 8, detail_score: 7, coherence_score: 9 },
    },
    {
      roundIndex: 3,
      evaluationId: feedback.evaluationId,
      question: thirdQuestion,
      answer: thirdAnswer,
      review: {
        ...review,
        totalScore: 22,
        question_fit_score: 8,
        detail_score: 7,
        coherence_score: 7,
        good_point: "3回目の回答が明確です。",
        improvement: "結果の数値を補足すると伝わります。",
      },
    },
  ];
  const { container } = render(
    <ThemeProvider theme={theme}>
      <FeedbackCard feedback={latestFeedback} followUpReviews={reviews} />
    </ThemeProvider>
  );
  const latest = screen.getByRole("region", { name: "今回の深掘り回答評価" });
  expect(latest).toHaveTextContent("3回目の回答が明確です。");
  expect(latest).toHaveTextContent("結果の数値を補足すると伝わります。");
  expect(latest).toHaveTextContent("22");
  expect(latest).not.toHaveTextContent("26");
  expect(container).toHaveTextContent("深掘り 1 回目の専用採点");
  expect(container).toHaveTextContent("深掘り 2 回目の専用採点");
  expect(container).toHaveTextContent("深掘り 3 回目の専用採点");
  expect(container).toHaveTextContent("26");
  expect(container).toHaveTextContent("24");
});

it("keeps the complete good and improvement text in a single card", () => {
  const good = "1行目の良かった点。\\n2行目も省略しません。";
  const improvement = "1行目の改善点。\\n2行目も省略しません。";
  render(
    <ThemeProvider theme={theme}>
      <FeedbackCard feedback={feedback} followUpReviews={[{
        ...item, review: { ...review, good_point: good, improvement },
      }]} />
    </ThemeProvider>
  );
  expect(screen.getByText(good)).toBeInTheDocument();
  expect(screen.getByText(improvement)).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "今回の深掘り回答評価" })).toContainElement(screen.getByText(good));
});
