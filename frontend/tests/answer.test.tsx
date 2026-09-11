/** @file answer.test.tsx @description 再読み込み時の未確定要求と再入力下書きの復元を検証する。 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { useAnswer } from "@/features/interview/hooks/useAnswer";
import { getEvaluation, submitAnswer } from "@/lib/api/interview";
import type { Session } from "@/lib/api/schemas";
vi.mock("@/lib/api/interview", () => ({
  getEvaluation: vi.fn(),
  submitAnswer: vi.fn(),
}));
const id = "00000000-0000-4000-8000-000000000001";
const key = "00000000-0000-4000-8000-000000000002";
const session: Session = {
  sessionId: id,
  questionNumber: 1,
  question: {
    id,
    category: "career",
    difficulty: "standard",
    question: "将来の目標は？",
  },
  activeAttempt: { attemptId: id, evaluationId: id, status: "completed" },
};
const storageKey = `pocket:answer:${id}`;
function mount(value = session, retryFrom: string | null = id) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useAnswer(value, retryFrom), { wrapper });
}
afterEach(() => {
  sessionStorage.clear();
  vi.resetAllMocks();
});
it.each(["completed", "processing"] as const)(
  "manually confirms pending request even when active attempt is %s",
  async (status) => {
    const body = { questionId: id, answer: "新しい回答です。" };
    sessionStorage.setItem(
      storageKey,
      JSON.stringify({
        version: 1,
        questionId: id,
        context: `1:${id}`,
        draft: body.answer,
        pending: { key, body },
      }),
    );
    vi.mocked(getEvaluation).mockResolvedValue({
      evaluationId: key,
      attemptId: key,
      status: "processing",
    });
    vi.mocked(submitAnswer).mockResolvedValue({
      attemptId: key,
      evaluationId: key,
      status: "processing",
    });
    const view = mount({
      ...session,
      activeAttempt: { ...session.activeAttempt!, status },
    });
    expect(view.result.current.phase).toBe("recovery_required");
    expect(getEvaluation).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(storageKey)).toContain(body.answer);
    await act(async () => {
      await view.result.current.send();
    });
    expect(submitAnswer).toHaveBeenCalledExactlyOnceWith(id, body, key);
    expect(view.result.current.phase).toBe("processing");
    view.unmount();
  },
);
it("restores a draft after retrying a failed evaluation and remounting", async () => {
  const failed: Session = {
    ...session,
    activeAttempt: { ...session.activeAttempt!, status: "failed" },
  };
  vi.mocked(getEvaluation).mockResolvedValue({
    evaluationId: id,
    attemptId: id,
    status: "failed",
    error: { code: "EVALUATION_FAILED", message: "failed" },
  });
  const first = mount(failed, null);
  await waitFor(() => expect(first.result.current.phase).toBe("failed"));
  act(() => first.result.current.retry());
  act(() =>
    first.result.current.form.setValue("answer", "再入力した下書きです。"),
  );
  await waitFor(() =>
    expect(sessionStorage.getItem(storageKey)).toContain(
      "再入力した下書きです。",
    ),
  );
  first.unmount();
  vi.mocked(getEvaluation).mockClear();
  const second = mount(failed, null);
  expect(second.result.current.phase).toBe("answering");
  expect(second.result.current.answer).toBe("再入力した下書きです。");
  expect(getEvaluation).not.toHaveBeenCalled();
  expect(sessionStorage.getItem(storageKey)).toContain(
    "再入力した下書きです。",
  );
  second.unmount();
});
