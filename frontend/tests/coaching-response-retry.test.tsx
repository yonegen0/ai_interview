/** @file coaching-response-retry.test.tsx @description 深掘り質問の取得失敗後に手動再確認で復帰できることを検証。 */
import { afterEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { CoachingResponse } from "@/features/feedback/components/organisms/CoachingResponse";
import { getQuestion } from "@/lib/api/interview";
import { feedbackV2Schema } from "@/lib/api/schemas";
import { scoreValues } from "@/lib/textLimits";
import { theme } from "@/theme/theme";
import {
  createQuestionFixture,
  createSessionFixture,
  storyIds,
  storyNow,
} from "../stories/fixtures";

vi.mock("@/lib/api/interview", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/interview")>()),
  getQuestion: vi.fn(),
}));

afterEach(() => vi.clearAllMocks());

it("shows a safe error and retries follow-up question retrieval with the keyboard", async () => {
  const answer = "本人の初回回答です。";
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
      status: "coaching",
      conclusion_score: 7,
      specificity_score: 7,
      reasoning_score: 7,
      good_point: "行動が明確です。",
      improvement: "成果の根拠を説明しましょう。",
      follow_up_question: "そのとき何をしましたか？",
      example: null,
    },
    ...scoreValues(answer, 7, 7, 7),
    createdAt: storyNow,
  });
  const followUpQuestion = "そのとき何をしましたか？";
  const recoveredSession = createSessionFixture({
    activeAttempt: {
      attemptId: storyIds.currentAttempt,
      evaluationId: storyIds.evaluation,
      status: "completed",
    },
    activeCoaching: {
      attemptId: storyIds.currentAttempt,
      evaluationId: storyIds.evaluation,
      stage: "awaiting_answer",
      initialAnswer: answer,
      latestAnswer: answer,
      coachingHistory: [],
      coachingCount: 0,
      followUpQuestion,
      lastSuccessfulEvaluationId: storyIds.evaluation,
    },
  });
  const fetchQuestion = vi.mocked(getQuestion);
  fetchQuestion
    .mockRejectedValueOnce(new Error("internal service details"))
    .mockResolvedValueOnce(recoveredSession);
  const client = new QueryClient({
    defaultOptions: { queries: { retryDelay: 0 } },
  });
  const user = userEvent.setup();
  const view = render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <CoachingResponse feedback={feedback} />
      </QueryClientProvider>
    </ThemeProvider>,
  );

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("現在の質問を取得できませんでした。");
  expect(alert).not.toHaveTextContent("internal service details");
  expect(fetchQuestion).toHaveBeenCalledTimes(1);

  const retry = screen.getByRole("button", { name: "もう一度確認する" });
  retry.focus();
  expect(retry).toHaveFocus();
  await user.keyboard("{Enter}");

  await waitFor(() => expect(fetchQuestion).toHaveBeenCalledTimes(2));
  await waitFor(() =>
    expect(screen.queryByText("現在の質問を取得できませんでした。")).not.toBeInTheDocument(),
  );
  expect(
    await screen.findByRole("heading", { name: "深掘り質問 1 / 3" }),
  ).toBeInTheDocument();
  expect(screen.getByText(followUpQuestion)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "あなたの回答" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "回答を送信" })).toBeDisabled();
  view.unmount();
  client.clear();
});
