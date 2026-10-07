/** @file answer-coaching.test.tsx @description Coaching recovery preserves drafts and failed inputs across navigation and retries. */
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { useAnswerOperation } from "@/hooks/useAnswerOperation";
import { getEvaluation, submitAnswer } from "@/lib/api/interview";
import { ApiError } from "@/lib/api/client";
import { answerRecoverySchema, readSaved, save } from "@/lib/storage/recovery";
import { auth } from "@/lib/auth/session";
import { createSessionFixture, storyIds } from "../stories/fixtures";
vi.mock("@/lib/api/interview", () => ({
  getEvaluation: vi.fn(),
  submitAnswer: vi.fn(),
}));
afterEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
});
it("returns a rejected retry to failed without resetting input or retrying automatically", async () => {
  const session = createSessionFixture({
    activeAttempt: {
      attemptId: storyIds.currentAttempt,
      evaluationId: storyIds.evaluation,
      status: "failed",
    },
    activeCoaching: {
      attemptId: storyIds.currentAttempt,
      evaluationId: storyIds.evaluation,
      stage: "failed",
      initialAnswer: "本人の送信済み回答です。",
      latestAnswer: "本人の送信済み回答です。",
      coachingHistory: [],
      coachingCount: 0,
      followUpQuestion: null,
      lastSuccessfulEvaluationId: null,
    },
  });
  save(`pocket:answer:${session.sessionId}`, {
    version: 1,
    questionId: session.question.id,
    context: "1:normal",
    draft: "古い下書きで初回入力へ戻さない",
  });
  vi.mocked(getEvaluation).mockResolvedValue({
    attemptId: storyIds.currentAttempt,
    evaluationId: storyIds.evaluation,
    feedbackVersion: 2,
    status: "failed",
    error: { code: "EVALUATION_FAILED", message: "failed" },
  });
  vi.mocked(submitAnswer).mockRejectedValue(
    new ApiError("VALIDATION_ERROR", 400),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const view = renderHook(() => useAnswerOperation(session, null), { wrapper });
  await waitFor(() => expect(view.result.current.phase).toBe("failed"));
  act(() => view.result.current.retry());
  await waitFor(() => expect(submitAnswer).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(view.result.current.phase).toBe("failed"));
  expect(vi.mocked(submitAnswer).mock.calls[0][1]).toEqual({
    kind: "retry_evaluation",
    attemptId: storyIds.currentAttempt,
    fromEvaluationId: storyIds.evaluation,
  });
  expect(view.result.current.error).toMatchObject({ status: 400 });
  expect(view.result.current.attempt?.evaluationId).toBe(storyIds.evaluation);
  expect(session.activeCoaching?.initialAnswer).toBe(
    "本人の送信済み回答です。",
  );
  view.unmount();
});

it.each([false, true])(
  "restores the follow-up draft after visiting current practice (cached evaluation: %s)",
  async (cached) => {
    const evaluation = {
      attemptId: storyIds.currentAttempt,
      evaluationId: storyIds.evaluation,
      status: "completed" as const,
      feedbackVersion: 2 as const,
    };
    const session = createSessionFixture({
      activeAttempt: evaluation,
      activeCoaching: {
        attemptId: storyIds.currentAttempt,
        evaluationId: storyIds.evaluation,
        stage: "awaiting_answer",
        initialAnswer: "本人の初回回答です。",
        latestAnswer: "本人の初回回答です。",
        coachingHistory: [],
        coachingCount: 0,
        followUpQuestion: "そのとき何をしましたか？",
        lastSuccessfulEvaluationId: storyIds.evaluation,
      },
    });
    const operation = {
      kind: "coaching_answer" as const,
      questionId: session.question.id,
      answer: "",
      attemptId: storyIds.currentAttempt,
      fromEvaluationId: storyIds.evaluation,
    };
    const key = `pocket:answer:${session.sessionId}`;
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const draft = "送信前の深掘り回答です。";
    const followUp = renderHook(
      () => useAnswerOperation(session, null, undefined, operation),
      { wrapper },
    );
    act(() => followUp.result.current.form.setValue("answer", draft));
    await waitFor(() =>
      expect(readSaved(key, answerRecoverySchema)?.draft).toBe(draft),
    );
    followUp.unmount();
    vi.mocked(getEvaluation).mockResolvedValue(evaluation);
    if (cached)
      client.setQueryData(
        [auth.scope(), "evaluation", evaluation.evaluationId],
        evaluation,
      );
    const practice = renderHook(() => useAnswerOperation(session, null), {
      wrapper,
    });
    await waitFor(() =>
      expect(practice.result.current.phase).toBe("completed"),
    );
    expect(readSaved(key, answerRecoverySchema)?.draft).toBe(draft);
    act(() => practice.result.current.discard());
    expect(readSaved(key, answerRecoverySchema)?.draft).toBe(draft);
    practice.unmount();
    const restored = renderHook(
      () => useAnswerOperation(session, null, undefined, operation),
      { wrapper },
    );
    expect(restored.result.current.answer).toBe(draft);
    expect(restored.result.current.phase).toBe("answering");
    expect(submitAnswer).not.toHaveBeenCalled();
    restored.unmount();
  },
);

it.each([
  { version: 1, context: "1:normal", status: "completed" },
  { version: 2, context: "1:normal:initial:new", status: "completed" },
  { version: 1, context: "1:normal", status: "failed" },
  { version: 2, context: "1:normal:initial:new", status: "failed" },
] as const)(
  "cleans up the operation's own v$version draft after $status",
  async ({ version, context, status }) => {
    const session = createSessionFixture({
      activeAttempt: {
        attemptId: storyIds.currentAttempt,
        evaluationId: storyIds.evaluation,
        status: "processing",
      },
    });
    const key = `pocket:answer:${session.sessionId}`;
    save(key, {
      version,
      questionId: session.question.id,
      context,
      draft: "評価済みの回答です。",
    });
    vi.mocked(getEvaluation).mockResolvedValue(
      status === "failed"
        ? {
            ...session.activeAttempt!,
            status,
            error: { code: "EVALUATION_FAILED", message: "failed" },
          }
        : { ...session.activeAttempt!, status },
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const view = renderHook(() => useAnswerOperation(session, null), {
      wrapper,
    });
    await waitFor(() => expect(view.result.current.phase).toBe(status));
    expect(readSaved(key, answerRecoverySchema)).toBeNull();
    view.unmount();
  },
);
