/** @file feedback-score-ui.test.tsx @description 評価種別ごとのスコア表示と欠損項目の非表示を検証する。 */
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { FeedbackScoreSummary } from "@/features/feedback/components/organisms/FeedbackScoreSummary";

it("shows authoritative Coaching V2 score, rank, three criteria, and length adjustments", () => {
  render(
    <FeedbackScoreSummary
      score={19}
      maximum={30}
      rank="B"
      description="追加の情報を確認して、回答を育てましょう。"
      breakdown={{ conclusion: 8, specificity: 5, reasoning: 7 }}
      answerLength={332}
      baseScore={20}
      lengthPenalty={1}
    />,
  );
  expect(screen.getByRole("heading", { name: "総合評価" })).toBeInTheDocument();
  expect(screen.getByText("19")).toBeInTheDocument();
  expect(screen.getByText("/ 30 · B")).toBeInTheDocument();
  expect(screen.getByText("B 評価")).toBeInTheDocument();
  expect(screen.getByText("8 / 10")).toBeInTheDocument();
  expect(screen.getByText("5 / 10")).toBeInTheDocument();
  expect(screen.getByText("7 / 10")).toBeInTheDocument();
  expect(screen.getByText("332 文字")).toBeInTheDocument();
  expect(screen.getByText("20 点")).toBeInTheDocument();
  expect(screen.getByText("1 点")).toBeInTheDocument();
});

it("keeps ordinary evaluation on a 100-point scale without inventing V2 fields", () => {
  render(<FeedbackScoreSummary score={0} maximum={100} description="回答を振り返りましょう。" />);
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.getByText("/ 100")).toBeInTheDocument();
  expect(screen.queryByText("結論")).not.toBeInTheDocument();
  expect(screen.queryByText("文字数減点")).not.toBeInTheDocument();
  expect(screen.queryByText(/評価$/)).not.toBeInTheDocument();
});
