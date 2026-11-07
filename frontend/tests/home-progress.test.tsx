/** @file home-progress.test.tsx @description ホーム進捗の表示とMock集計。 */
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { expect, it, vi } from "vitest";
import { HomeProgress, progressMessage } from "@/features/home/components/organisms/HomeProgress";
import { getPracticeProgress } from "@/lib/api/practiceProgress";
import { mockPracticeProgress } from "@/mocks/practiceProgress";
import { createRepository } from "@/mocks/store";
import { theme } from "@/theme/theme";

vi.mock("@/lib/api/practiceProgress", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/practiceProgress")>()),
  getPracticeProgress: vi.fn(),
}));

const renderCard = async (completed: number, total = 15) => {
  vi.mocked(getPracticeProgress).mockResolvedValue({
    bankVersion: 0, totalQuestions: total, completedQuestions: completed,
    nextIncompleteQuestionId: completed === total ? null : "11111111-1111-4111-8111-111111111111",
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ThemeProvider theme={theme}><HomeProgress /></ThemeProvider>
    </QueryClientProvider>,
  );
  await screen.findByText(`${completed} / ${total}`, { exact: false });
};

it.each([0, 5, 10, 15])("renders %i completed questions", async (completed) => {
  await renderCard(completed);
  expect(screen.getByText(`${completed} / 15`, { exact: false })).toBeInTheDocument();
  if (completed === 15) expect(screen.getByText("全問達成")).toBeInTheDocument();
  else expect(screen.getByText(`あと${15 - completed}問`)).toBeInTheDocument();
});

it("supports zero-question bank without false achievement", () => {
  expect(progressMessage(0, 0)).toContain("練習できる質問がありません");
  expect(progressMessage(15, 15)).toContain("全15問達成");
});

it("mock counts only completed owner-scoped question IDs", () => {
  const repo = createRepository();
  const state = repo.read();
  const q = state.bank.questions[0];
  expect(mockPracticeProgress(state, "mock-user").completedQuestions).toBe(0);
  state.attempts["a"] = {
    feedback: {
      attemptId: "a", sessionId: "s", question: q, questionNumber: 1,
      answer: "test", score: 0, summary: "ok", strengths: ["ok"],
      improvements: ["ok"], createdAt: new Date().toISOString(),
    },
    evaluation: { attemptId: "a", evaluationId: "e", status: "completed" },
    polls: 0, startedAt: Date.now(),
  };
  state.owners.s = "mock-user";
  expect(mockPracticeProgress(state, "mock-user").completedQuestions).toBe(1);
  expect(mockPracticeProgress(state, "other").completedQuestions).toBe(0);
});
