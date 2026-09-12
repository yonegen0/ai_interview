/** @file practice.test.tsx @description 回答フォームを実API ClientとMSWで統合検証 */
import { afterAll, afterEach, beforeAll, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { createRepository } from "@/mocks/store";
import { createHandlers, type Scenario } from "@/mocks/handlers";
import { createSession, getQuestion } from "@/lib/api/interview";
import { PracticeForm } from "@/features/interview/components/templates/PracticeForm";
import { theme } from "@/theme/theme";
import type { Session } from "@/lib/api/schemas";
import { save } from "@/lib/storage/recovery";
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));
const repository = createRepository();
let scenario: Scenario = "success";
let answerRequests = 0;
const server = setupServer(
  ...createHandlers(repository, () => scenario, "http://localhost/api"),
);
beforeAll(() => {
  server.events.on("request:start", ({ request }) => {
    if (request.method === "POST" && new URL(request.url).pathname.endsWith("/answers")) {
      answerRequests += 1;
    }
  });
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost/api");
  server.listen();
});
afterEach(() => {
  repository.reset();
  scenario = "success";
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
        <PracticeForm session={session} retryFrom={null} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}
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

it.each(["あ".repeat(500), "😀".repeat(250)])(
  "counts UTF-16 units, retains overlong input and prevents POST until corrected (%#)",
  async (validAnswer) => {
    const view = await mount();
    const input = screen.getByLabelText("あなたの回答");
    fireEvent.change(input, { target: { value: validAnswer } });
    await screen.findByText("500 / 500文字 · 100〜300文字がおすすめです");
    fireEvent.change(input, { target: { value: validAnswer + "あ" } });
    await screen.findByText("500文字以内で入力してください。");
    expect(input).toHaveValue(validAnswer + "あ");
    const button = screen.getByRole("button", { name: "回答を送信" });
    expect(button).toBeDisabled();
    fireEvent.submit(button.closest("form")!);
    await screen.findByText("500文字以内で入力してください。");
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
  const view = await mount((session) => { savedSession = session; });
  const answer = "あ".repeat(501);
  fireEvent.change(screen.getByLabelText("あなたの回答"), { target: { value: answer } });
  await screen.findByText("500文字以内で入力してください。");
  view.unmount();
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const restored = render(
    <ThemeProvider theme={theme}><QueryClientProvider client={client}>
      <PracticeForm session={savedSession!} retryFrom={null} />
    </QueryClientProvider></ThemeProvider>,
  );
  const input = screen.getByLabelText("あなたの回答");
  expect(input).toHaveValue(answer);
  fireEvent.submit(screen.getByRole("button", { name: "回答を送信" }).closest("form")!);
  await screen.findByText("500文字以内で入力してください。");
  expect(answerRequests).toBe(0);
  fireEvent.change(input, { target: { value: answer.slice(0, 500) } });
  const button = screen.getByRole("button", { name: "回答を送信" });
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.click(button);
  await screen.findByText("回答を確認しています");
  expect(answerRequests).toBe(1);
  restored.unmount();
});

it("does not restore or automatically send an obsolete overlong pending request", async () => {
  const view = await mount((session) => {
    save(`pocket:answer:${session.sessionId}`, {
      version: 1, questionId: session.question.id, context: "1:normal",
      draft: "同居していた下書き", pending: {
        key: crypto.randomUUID(), body: { questionId: session.question.id, answer: "あ".repeat(501) },
      },
    });
  });
  expect(screen.getByLabelText("あなたの回答")).toHaveValue("");
  expect(screen.queryByRole("button", { name: "送信結果を再確認" })).not.toBeInTheDocument();
  expect(answerRequests).toBe(0);
  view.unmount();
});
