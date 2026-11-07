/** @file practice-quick.test.tsx @description Quick entry and recovery behavior without AI or AWS. */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { theme } from "@/theme/theme";
import { HomeNavigation } from "@/features/home/components/organisms/HomeNavigation";
import { PracticeSelector } from "@/features/interview/components/organisms/PracticeSelector";
import { PracticeQuick } from "@/features/interview/components/pages/PracticeQuick";
import { getPracticeProgress, getPracticeResume } from "@/lib/api/practiceProgress";
import { createSession, getQuestion } from "@/lib/api/interview";
import { ApiError } from "@/lib/api/client";

const mock = vi.hoisted(() => {
  const saved = new Map<string, unknown>();
  const replace = vi.fn();
  const router = { replace };
  const isActive = () => true;
  const storage = {
    readSaved: (key: string) => saved.get(key) ?? null,
    save: (key: string, value: unknown) => { saved.set(key, value); return true; },
    removeSaved: (key: string) => { saved.delete(key); },
  };
  return { saved, replace, router, storage, isActive };
});
vi.mock("next/navigation", () => ({ useRouter: () => mock.router }));
vi.mock("@/hooks/useOperationScope", () => ({
  useOperationScope: () => ({
    scope: "quick-test-scope:",
    isActive: mock.isActive,
    storage: mock.storage,
  }),
}));
vi.mock("@/lib/api/practiceProgress", () => ({
  getPracticeProgress: vi.fn(),
  getPracticeResume: vi.fn(),
}));
vi.mock("@/lib/api/interview", () => ({
  createSession: vi.fn(),
  getQuestion: vi.fn(),
}));

const QUESTION_ID = "f1500000-0000-4000-8000-000000000001";
const SESSION_ID = "11000000-0000-4000-8000-000000000001";
const REQUEST_KEY = "12000000-0000-4000-8000-000000000001";
const progress = (completed = 0, total = 15) => ({
  bankVersion: 0,
  totalQuestions: total,
  completedQuestions: completed,
  nextIncompleteQuestionId: completed < total ? QUESTION_ID : null,
});

const mount = (node: React.ReactNode) => render(
  <ThemeProvider theme={theme}>{node}</ThemeProvider>,
);
beforeEach(() => {
  vi.mocked(getPracticeProgress).mockResolvedValue(progress());
  vi.mocked(getPracticeResume).mockResolvedValue({ status: "none" });
  vi.mocked(createSession).mockResolvedValue({ sessionId: SESSION_ID });
  vi.mocked(getQuestion).mockResolvedValue({
    sessionId: SESSION_ID,
    question: { id: QUESTION_ID, category: "self_introduction", difficulty: "standard", question: "質問" },
    questionNumber: 1,
    activeAttempt: null,
    mode: "quick",
    totalQuestions: 1,
    hasNext: false,
  });
});
afterEach(() => {
  cleanup();
  mock.saved.clear();
  mock.replace.mockReset();
  vi.resetAllMocks();
  sessionStorage.clear();
});

it("separates the two home actions", () => {
  mount(<HomeNavigation />);
  expect(screen.getByRole("link", { name: /カテゴリから選ぶ/ }).getAttribute("href"))
    .toMatch(/^\/practice\/category\/?$/);
  expect(screen.getByRole("link", { name: /3分から始める/ }).getAttribute("href"))
    .toMatch(/^\/practice\/quick\/?$/);
});

it("category-only selector has no practice mode chooser", () => {
  mount(<PracticeSelector categoryOnly view={{
    mode: "category", category: null,
    options: {
      bankVersion: 0, totalQuestions: 15,
      categories: [{ id: "career", label: "キャリア", questionCount: 2 }],
    },
    loading: false, optionsError: null, error: null,
    disabled: false, canStart: false, starting: false, recovering: false,
  }} actions={{
    selectMode: vi.fn(), selectCategory: vi.fn(),
    start: vi.fn(async () => {}), refresh: vi.fn(),
  }} />);
  expect(screen.getByRole("combobox", { name: "練習するカテゴリ" })).toBeInTheDocument();
  expect(screen.queryByText("全質問を順番に練習")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "ホームへ戻る" })).toBeInTheDocument();
});

it("automatically creates exactly one quick session for the first incomplete ID", async () => {
  mount(<PracticeQuick />);
  await waitFor(() => expect(mock.replace).toHaveBeenCalledWith(
    `/practice/session/?sessionId=${SESSION_ID}`,
  ));
  expect(getPracticeProgress).toHaveBeenCalledTimes(1);
  expect(getPracticeResume).toHaveBeenCalledWith(QUESTION_ID, undefined, undefined);
  expect(createSession).toHaveBeenCalledTimes(1);
  expect(createSession).toHaveBeenCalledWith({
    mode: "quick", questionId: QUESTION_ID, bankVersion: 0, difficulty: "standard",
  }, expect.any(String));
  expect(mock.saved.has("pocket:create:quick")).toBe(false);
});

it("restores an unresolved start operation with the original idempotency key", async () => {
  const body = {
    mode: "quick", questionId: QUESTION_ID, bankVersion: 0, difficulty: "standard",
  };
  mock.saved.set("pocket:create:quick", { version: 1, key: REQUEST_KEY, body });
  mount(<PracticeQuick />);
  await waitFor(() => expect(mock.replace).toHaveBeenCalledTimes(1));
  expect(createSession).toHaveBeenCalledWith(body, REQUEST_KEY);
  expect(getPracticeProgress).not.toHaveBeenCalled();
  expect(mock.saved.size).toBe(0);
});

it("restarts from latest progress after a definitive rejection of a saved create", async () => {
  const oldBody = {
    mode: "quick", questionId: QUESTION_ID, bankVersion: 0, difficulty: "standard",
  };
  mock.saved.set("pocket:create:quick", { version: 1, key: REQUEST_KEY, body: oldBody });
  vi.mocked(createSession).mockRejectedValueOnce(new ApiError("QUESTION_BANK_CONFLICT", 409));

  mount(<PracticeQuick />);
  const retry = await screen.findByRole("button", { name: "最新の未完了質問から再試行" });
  expect(mock.saved.has("pocket:create:quick")).toBe(false);
  expect(createSession).toHaveBeenCalledWith(oldBody, REQUEST_KEY);
  expect(getPracticeProgress).not.toHaveBeenCalled();

  fireEvent.click(retry);
  await waitFor(() => expect(mock.replace).toHaveBeenCalledWith(
    `/practice/session/?sessionId=${SESSION_ID}`,
  ));
  expect(getPracticeProgress).toHaveBeenCalledTimes(1);
  expect(getPracticeResume).toHaveBeenCalledTimes(1);
  expect(createSession).toHaveBeenCalledTimes(2);
  expect(vi.mocked(createSession).mock.calls[1][1]).not.toBe(REQUEST_KEY);
  expect(mock.saved.has("pocket:create:quick")).toBe(false);
});

it.each([
  ["timeout", new ApiError("TIMEOUT")],
  ["unconfirmed authentication", new ApiError("UNAUTHORIZED", 401)],
])("keeps the exact saved operation after %s during recovery", async (_case, failure) => {
  const body = {
    mode: "quick", questionId: QUESTION_ID, bankVersion: 0, difficulty: "standard",
  };
  const operation = { version: 1, key: REQUEST_KEY, body };
  mock.saved.set("pocket:create:quick", operation);
  vi.mocked(createSession).mockRejectedValueOnce(failure);

  mount(<PracticeQuick />);
  const retry = await screen.findByRole("button", { name: "同じ操作で再確認する" });
  expect(mock.saved.get("pocket:create:quick")).toEqual(operation);
  expect(getPracticeProgress).not.toHaveBeenCalled();

  fireEvent.click(retry);
  await waitFor(() => expect(mock.replace).toHaveBeenCalledWith(
    `/practice/session/?sessionId=${SESSION_ID}`,
  ));
  expect(createSession).toHaveBeenCalledTimes(2);
  expect(createSession).toHaveBeenNthCalledWith(1, body, REQUEST_KEY);
  expect(createSession).toHaveBeenNthCalledWith(2, body, REQUEST_KEY);
  expect(getPracticeProgress).not.toHaveBeenCalled();
  expect(mock.saved.has("pocket:create:quick")).toBe(false);
});

it("restores the original draft session without creating or copying", async () => {
  vi.mocked(getPracticeResume).mockResolvedValue({
    status: "resume", reason: "draft", sessionId: SESSION_ID,
  });
  mount(<PracticeQuick />);
  await waitFor(() => expect(mock.replace).toHaveBeenCalledTimes(1));
  expect(getQuestion).toHaveBeenCalledWith(SESSION_ID);
  expect(createSession).not.toHaveBeenCalled();
});

it("passes a pending tab-local operation to owner-checked restore search", async () => {
  sessionStorage.setItem(`quick-test-scope:pocket:answer:${SESSION_ID}`, JSON.stringify({
    version: 3, questionId: QUESTION_ID, context: "1:normal:initial:new",
    draft: "途中の回答", pending: {
      key: REQUEST_KEY, body: { questionId: QUESTION_ID, answer: "途中の回答" },
    },
  }));
  vi.mocked(getPracticeResume).mockResolvedValue({
    status: "resume", reason: "local", sessionId: SESSION_ID, questionNumber: 1,
  });
  mount(<PracticeQuick />);
  await waitFor(() => expect(mock.replace).toHaveBeenCalledTimes(1));
  expect(getPracticeResume).toHaveBeenCalledWith(QUESTION_ID, SESSION_ID, true);
  expect(createSession).not.toHaveBeenCalled();
});

it("all questions complete renders achievement with no session creation", async () => {
  vi.mocked(getPracticeProgress).mockResolvedValue(progress(15, 15));
  mount(<PracticeQuick />);
  expect(await screen.findByRole("heading", {
    name: "全15問達成！おめでとうございます",
  })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "カテゴリから復習する" }).getAttribute("href"))
    .toMatch(/^\/practice\/category\/?$/);
  expect(createSession).not.toHaveBeenCalled();
});

it("zero-question bank does not display achievement", async () => {
  vi.mocked(getPracticeProgress).mockResolvedValue(progress(0, 0));
  mount(<PracticeQuick />);
  expect(await screen.findByRole("heading", {
    name: "練習できる質問がありません",
  })).toBeInTheDocument();
  expect(createSession).not.toHaveBeenCalled();
});

it("unavailable restore search must not start another session", async () => {
  vi.mocked(getPracticeResume).mockRejectedValue(new ApiError("PRACTICE_RESUME_UNAVAILABLE", 503));
  mount(<PracticeQuick />);
  expect(await screen.findByRole("heading", {
    name: "練習を確認できませんでした",
  })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "同じ操作で再確認する" }))
    .toBeInTheDocument();
  expect(createSession).not.toHaveBeenCalled();
});

it("changed question protects drafts instead of creating a new session", async () => {
  vi.mocked(getPracticeResume).mockResolvedValue({ status: "changed" });
  mount(<PracticeQuick />);
  expect(await screen.findByRole("heading", {
    name: "質問が更新されました",
  })).toBeInTheDocument();
  expect(createSession).not.toHaveBeenCalled();
});
