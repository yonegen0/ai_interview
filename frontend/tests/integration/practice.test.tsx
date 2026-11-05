/** @file practice.test.tsx @description 回答フォームを実API ClientとMSWで統合検証 */
import { afterAll, afterEach, beforeAll, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { createRepository } from "@/mocks/store";
import { createHandlers, type Scenario } from "@/mocks/handlers";
import { createSession, getQuestion, submitAnswer } from "@/lib/api/interview";
import { PracticeSessionContent } from "@/features/interview/components/pages/PracticeSessionContent";
import { InterviewPractice } from "@/features/interview/components/pages/InterviewPractice";
import { auth } from "@/lib/auth/session";
import { theme } from "@/theme/theme";
import type { Session } from "@/lib/api/schemas";
import { save, readSaved, answerRecoverySchema } from "@/lib/storage/recovery";
const { push, practiceLocation } = vi.hoisted(() => ({
  push: vi.fn(),
  practiceLocation: { search: "" },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(practiceLocation.search),
}));
const repository = createRepository();
let scenario: Scenario = "success";
let answerRequests = 0;
const server = setupServer(
  ...createHandlers(repository, () => scenario, "http://localhost/api"),
);
beforeAll(() => {
  server.events.on("request:start", ({ request }) => {
    if (
      request.method === "POST" &&
      new URL(request.url).pathname.endsWith("/answers")
    ) {
      answerRequests += 1;
    }
  });
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost/api");
  server.listen();
});
afterEach(() => {
  repository.reset();
  scenario = "success";
  practiceLocation.search = "";
  sessionStorage.clear();
  push.mockClear();
  answerRequests = 0;
});
afterAll(() => {
  server.close();
  vi.unstubAllEnvs();
});
async function mount(seed?: (session: Session) => void) {
  const created = await createSession("career", crypto.randomUUID());
  const session = await getQuestion(created.sessionId);
  seed?.(session);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <PracticeSessionContent session={session} retryFrom={null} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}
it("keeps the answer label floated when empty and after entering text and blurring", async () => {
  const view = await mount();
  const user = userEvent.setup();
  const input = screen.getByLabelText("あなたの回答");
  const label = input.closest(".MuiFormControl-root")?.querySelector("label");
  expect(label).toHaveClass("MuiInputLabel-shrink");
  await user.type(input, "営業に挑戦したいです。");
  await user.tab();
  expect(input).toHaveValue("営業に挑戦したいです。");
  expect(label).toHaveClass("MuiInputLabel-shrink");
  view.unmount();
});

it("submits once on rapid form submission and reaches feedback", async () => {
  const view = await mount();
  const user = userEvent.setup();
  await user.type(
    screen.getByLabelText("あなたの回答"),
    "チームで改善しました。",
  );
  const form = screen
    .getByRole("button", { name: "回答を送信" })
    .closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  await screen.findByText("回答を確認しています");
  await waitFor(
    () =>
      expect(push).toHaveBeenCalledWith(
        expect.stringContaining("/result/?attemptId="),
      ),
    { timeout: 8000 },
  );
  expect(Object.keys(repository.read().attempts)).toHaveLength(1);
  view.unmount();
}, 12000);
it("retains immutable pending request after response loss", async () => {
  await mount();
  scenario = "response_lost";
  await userEvent.type(screen.getByLabelText("あなたの回答"), "回答です。");
  await userEvent.click(screen.getByRole("button", { name: "回答を送信" }));
  const retry = await screen.findByRole("button", { name: "送信結果を再確認" });
  expect(screen.getByLabelText("あなたの回答")).toBeDisabled();
  await userEvent.click(retry);
  await screen.findByText("回答を確認しています");
  expect(Object.keys(repository.read().attempts)).toHaveLength(1);
});

it.each(["あ".repeat(400), "😀".repeat(400)])(
  "counts Unicode code points, retains overlong input and prevents POST until corrected (%#)",
  async (validAnswer) => {
    const view = await mount();
    const input = screen.getByLabelText("あなたの回答");
    fireEvent.change(input, { target: { value: validAnswer } });
    await screen.findByText("400 / 400文字");
    fireEvent.change(input, { target: { value: validAnswer + "あ" } });
    await screen.findByText("400文字以内で入力してください。");
    expect(input).toHaveValue(validAnswer + "あ");
    const button = screen.getByRole("button", { name: "回答を送信" });
    expect(button).toBeDisabled();
    fireEvent.submit(button.closest("form")!);
    await screen.findByText("400文字以内で入力してください。");
    expect(answerRequests).toBe(0);
    fireEvent.change(input, { target: { value: validAnswer } });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await screen.findByText("回答を確認しています");
    expect(answerRequests).toBe(1);
    expect(Object.keys(repository.read().attempts)).toHaveLength(1);
    view.unmount();
  },
);

it("restores an overlong draft across remount and allows correction", async () => {
  let savedSession: Session;
  const view = await mount((session) => {
    savedSession = session;
  });
  const answer = "あ".repeat(501);
  fireEvent.change(screen.getByLabelText("あなたの回答"), {
    target: { value: answer },
  });
  await screen.findByText("400文字以内で入力してください。");
  view.unmount();
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  const restored = render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <PracticeSessionContent session={savedSession!} retryFrom={null} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
  const input = screen.getByLabelText("あなたの回答");
  expect(input).toHaveValue(answer);
  fireEvent.submit(
    screen.getByRole("button", { name: "回答を送信" }).closest("form")!,
  );
  await screen.findByText("400文字以内で入力してください。");
  expect(answerRequests).toBe(0);
  fireEvent.change(input, { target: { value: answer.slice(0, 400) } });
  const button = screen.getByRole("button", { name: "回答を送信" });
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.click(button);
  await screen.findByText("回答を確認しています");
  expect(answerRequests).toBe(1);
  restored.unmount();
});

it("reconfirms a valid V1 pending 500-unit answer with its original payload", async () => {
  const original = "x".repeat(500);
  const view = await mount((session) => {
    save(`pocket:answer:${session.sessionId}`, {
      version: 1,
      questionId: session.question.id,
      context: "1:normal",
      draft: original,
      pending: {
        key: crypto.randomUUID(),
        body: { questionId: session.question.id, answer: original },
      },
    });
  });
  expect(screen.getByLabelText("あなたの回答")).toHaveValue(original);
  expect(answerRequests).toBe(0);
  await userEvent.click(
    screen.getByRole("button", { name: "送信結果を再確認" }),
  );
  await screen.findByText("回答を確認しています");
  const records = Object.values(repository.read().attempts);
  expect(records).toHaveLength(1);
  expect(records[0].feedback.answer).toBe(original);
  expect(records[0].feedback).not.toHaveProperty("feedbackVersion");
  expect(answerRequests).toBe(1);
  view.unmount();
});

it("does not restore or automatically send an obsolete overlong pending request", async () => {
  const view = await mount((session) => {
    save(`pocket:answer:${session.sessionId}`, {
      version: 1,
      questionId: session.question.id,
      context: "1:normal",
      draft: "同居していた下書き",
      pending: {
        key: crypto.randomUUID(),
        body: { questionId: session.question.id, answer: "あ".repeat(501) },
      },
    });
  });
  expect(screen.getByLabelText("あなたの回答")).toHaveValue("");
  expect(
    screen.queryByRole("button", { name: "送信結果を再確認" }),
  ).not.toBeInTheDocument();
  expect(answerRequests).toBe(0);
  view.unmount();
});


it("shows the previous-answer copy only for a retry and preserves edited text on cancel", async () => {
  const created = await createSession("career", crypto.randomUUID());
  const session = await getQuestion(created.sessionId);
  const previous = "前回正式送信した回答です。";
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <PracticeSessionContent
          session={session}
          retryFrom={crypto.randomUUID()}
          previousAnswer={previous}
        />
      </QueryClientProvider>
    </ThemeProvider>,
  );
  const input = screen.getByLabelText("あなたの回答");
  expect(screen.getByText("250〜330文字がおすすめです")).toBeInTheDocument();
  expect(input).toHaveValue(previous);
  const copy = screen.getByRole("button", { name: "前回の回答をコピー" });
  await userEvent.click(copy);
  expect(screen.queryByText("入力中の回答を上書きしますか？")).not.toBeInTheDocument();
  fireEvent.change(input, { target: { value: "編集中の別の回答" } });
  await userEvent.click(copy);
  expect(screen.getByText("入力中の回答を上書きしますか？")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));
  expect(input).toHaveValue("編集中の別の回答");
  await userEvent.click(copy);
  await userEvent.click(screen.getByRole("button", { name: "前回の回答に置き換える" }));
  expect(input).toHaveValue(previous);
  await screen.findByText(`${Array.from(previous).length} / 400文字`);
  expect(input.closest(".MuiFormControl-root")?.querySelector("label")).toHaveClass(
    "MuiInputLabel-shrink",
  );
  expect(answerRequests).toBe(0);
  view.unmount();
});

it("does not show a previous-answer copy for an initial answer", async () => {
  const view = await mount();
  expect(screen.getByText("250〜330文字がおすすめです")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "前回の回答をコピー" })).not.toBeInTheDocument();
  view.unmount();
});

/** Exercise usePracticeSession as well as the existing PR #123 copy UI. */
async function mountNormalSession(session: Session) {
  practiceLocation.search = `sessionId=${session.sessionId}`;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <InterviewPractice />
      </QueryClientProvider>
    </ThemeProvider>,
  );
  return { view, client };
}

it("offers previous accepted answer across normal sessions, only copies on click and preserves draft choices", async () => {
  const historic = await createSession("career", crypto.randomUUID());
  const historicSession = await getQuestion(historic.sessionId);
  const previous = "前回の正式回答です。";
  await submitAnswer(historic.sessionId, {
    questionId: historicSession.question.id,
    answer: previous,
  }, crypto.randomUUID());
  const current = await createSession("career", crypto.randomUUID());
  const session = await getQuestion(current.sessionId);
  expect(session.question.id).toBe(historicSession.question.id);
  const { view } = await mountNormalSession(session);
  const input = await screen.findByLabelText("あなたの回答");
  expect(input).toHaveValue("");
  const copy = await screen.findByRole("button", { name: "前回の回答をコピー" });
  expect(input).toHaveValue("");
  await userEvent.click(copy);
  expect(input).toHaveValue(previous);
  expect(answerRequests).toBe(1);
  fireEvent.change(input, { target: { value: "編集中の下書きです。" } });
  await userEvent.click(copy);
  await screen.findByText("入力中の回答を上書きしますか？");
  await userEvent.click(screen.getByRole("button", { name: "キャンセル" }));
  expect(input).toHaveValue("編集中の下書きです。");
  await userEvent.click(copy);
  await userEvent.click(screen.getByRole("button", { name: "前回の回答に置き換える" }));
  expect(input).toHaveValue(previous);
  await screen.findByText(`${Array.from(previous).length} / 400文字`);
  expect(answerRequests).toBe(1); // Only the historical POST; copy never sends.
  await waitFor(() =>
    expect(readSaved(`pocket:answer:${session.sessionId}`, answerRecoverySchema)?.draft)
      .toBe(previous),
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  fireEvent.change(input, { target: { value: "コピーを編集して送信します。" } });
  await waitFor(() =>
    expect(screen.queryByText("入力中の回答を上書きしますか？")).not.toBeInTheDocument(),
  );
  await userEvent.click(screen.getByRole("button", { name: "回答を送信" }));
  await waitFor(() =>
    expect(Object.values(repository.read().attempts).some(
      (entry) => entry.feedback.answer === "コピーを編集して送信します。",
    )).toBe(true),
  );
  expect(answerRequests).toBe(2);
  view.unmount();
});

it("does not show answers from other questions or other authenticated owners", async () => {
  const historical = await createSession("career", crypto.randomUUID());
  const previousSession = await getQuestion(historical.sessionId);
  await submitAnswer(historical.sessionId, {
    questionId: previousSession.question.id, answer: "秘密の本人回答です。",
  }, crypto.randomUUID());
  const otherCategory = await createSession("motivation", crypto.randomUUID());
  const otherSession = await getQuestion(otherCategory.sessionId);
  expect(otherSession.question.id).not.toBe(previousSession.question.id);
  const first = await mountNormalSession(otherSession);
  await screen.findByLabelText("あなたの回答");
  expect(screen.queryByRole("button", { name: "前回の回答をコピー" })).not.toBeInTheDocument();
  first.view.unmount();

  auth.setMockActor("mock-admin", ["ADMIN"]);
  const adminSessionId = await createSession("career", crypto.randomUUID());
  const adminSession = await getQuestion(adminSessionId.sessionId);
  const second = await mountNormalSession(adminSession);
  await screen.findByLabelText("あなたの回答");
  expect(screen.queryByRole("button", { name: "前回の回答をコピー" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("あなたの回答")).toHaveValue("");
  second.view.unmount();
});

it("history fetch failures never block normal typing or submitting", async () => {
  server.use(http.get("http://localhost/api/questions/:id/previous-answer", () =>
    HttpResponse.json({ code: "INTERNAL_SERVER_ERROR", message: "unavailable" }, { status: 500 }),
  ));
  const created = await createSession("career", crypto.randomUUID());
  const session = await getQuestion(created.sessionId);
  const { view } = await mountNormalSession(session);
  const input = await screen.findByLabelText("あなたの回答");
  expect(screen.queryByRole("button", { name: "前回の回答をコピー" })).not.toBeInTheDocument();
  await userEvent.type(input, "履歴が見られなくても入力可能です。");
  await userEvent.click(screen.getByRole("button", { name: "回答を送信" }));
  await waitFor(() =>
    expect(Object.values(repository.read().attempts).some(
      (entry) => entry.feedback.answer === "履歴が見られなくても入力可能です。",
    )).toBe(true),
  );
  view.unmount();
});
