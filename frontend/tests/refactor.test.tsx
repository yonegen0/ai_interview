/** @file refactor.test.tsx @description 分割した画面の固定要求・競合・OTP・遷移境界を検証する。 */
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import type { ReactNode } from "react";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  expect,
  it,
  vi,
} from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { createHandlers } from "@/mocks/handlers";
import { createRepository } from "@/mocks/store";
import { auth } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/client";
import { theme } from "@/theme/theme";
import { QuestionManagement } from "@/features/admin/components/pages/QuestionManagement";
import { useEmailOtpLogin } from "@/features/auth/hooks/useEmailOtpLogin";
import { usePracticeController } from "@/features/interview/hooks/usePracticeController";
import { useAccountActions } from "@/hooks/useAccountActions";
import { changeSummary } from "@/features/admin/model/editor";
import { safeReturn } from "@/features/auth/model/login";
import { createBankFixture } from "../stories/fixtures/refactor";
import { createCompletedState, storyIds } from "../stories/fixtures";
import { resetRecoveryMemoryForTests, readSaved } from "@/lib/storage/recovery";
import { savedBankSchema, storageKey } from "@/features/admin/model/editor";
const { push, replace } = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  useSearchParams: () =>
    new URLSearchParams("returnTo=%2Fadmin%2Fquestions%2F"),
  usePathname: () => "/login/",
}));
const repository = createRepository();
const server = setupServer(
  ...createHandlers(repository, () => "success", "http://localhost/api"),
);
const clients: QueryClient[] = [];
function environment() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
  return { client, wrapper };
}
beforeAll(() => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost/api");
  server.listen({ onUnhandledRequest: "error" });
});
beforeEach(() => {
  repository.write({ ...repository.read(), bank: createBankFixture(1) });
  auth.setMockActor("mock-admin", ["ADMIN"]);
});
afterEach(() => {
  for (const client of clients.splice(0)) client.clear();
  server.resetHandlers();
  repository.reset();
  sessionStorage.clear();
  resetRecoveryMemoryForTests();
  vi.restoreAllMocks();
  vi.useRealTimers();
  push.mockClear();
  replace.mockClear();
});
afterAll(() => {
  server.close();
  vi.unstubAllEnvs();
});
async function confirmEdit() {
  const input = (await screen.findAllByLabelText("質問本文"))[0];
  fireEvent.change(input, { target: { value: "変更した質問です。" } });
  const confirm = screen.getByRole("button", { name: "保存内容を確認" });
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  await screen.findByRole("button", { name: "保存して反映" });
  return input;
}
it("reconfirms exactly the same snapshot and key after response loss", async () => {
  const requests: { body: unknown; key: string | null }[] = [];
  server.use(
    http.post(
      "http://localhost/api/admin/question-bank",
      async ({ request }) => {
        requests.push({
          body: await request.json(),
          key: request.headers.get("Idempotency-Key"),
        });
        return requests.length === 1
          ? HttpResponse.error()
          : HttpResponse.json({
              version: 1,
              totalQuestions: 1,
              updatedAt: "2026-10-06T00:00:00.000Z",
            });
      },
    ),
  );
  render(<QuestionManagement />, { wrapper: environment().wrapper });
  const input = await confirmEdit();
  expect(input).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "保存して反映" }));
  const reconfirm = await screen.findByRole("button", {
    name: "保存結果を再確認",
  });
  expect(screen.getByRole("button", { name: "質問を追加" })).toBeDisabled();
  const saved = readSaved(storageKey, savedBankSchema);
  expect(saved?.pending?.body.questions[0].question).toBe("変更した質問です。");
  fireEvent.click(reconfirm);
  await screen.findByText(/質問一覧を保存しました/);
  expect(requests).toHaveLength(2);
  expect(requests[1]).toEqual(requests[0]);
  expect(requests[0].key).toBe(saved?.pending?.key);
  expect(screen.getByRole("button", { name: "保存内容を確認" })).toBeDisabled();
});
it("keeps conflicting edits as a reference when adopting the latest bank", async () => {
  server.use(
    http.post("http://localhost/api/admin/question-bank", () =>
      HttpResponse.json(
        { code: "QUESTION_BANK_CONFLICT", message: "conflict" },
        { status: 409 },
      ),
    ),
  );
  render(<QuestionManagement />, { wrapper: environment().wrapper });
  await confirmEdit();
  fireEvent.click(screen.getByRole("button", { name: "保存して反映" }));
  await screen.findByRole("heading", { name: "最新版との比較" });
  expect(screen.getAllByLabelText("質問本文")[0]).toHaveValue(
    "変更した質問です。",
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "最新版で編集し直す" }),
  );
  await screen.findByRole("heading", { name: "変更前の編集内容（参照用）" });
  expect(screen.getByText("1. 変更した質問です。")).toBeInTheDocument();
  expect(screen.getAllByLabelText("質問本文")[0]).toBeEnabled();
});
it("blocks editing after an ADMIN save returns 403", async () => {
  server.use(
    http.post("http://localhost/api/admin/question-bank", () =>
      HttpResponse.json(
        { code: "FORBIDDEN", message: "forbidden" },
        { status: 403 },
      ),
    ),
  );
  render(<QuestionManagement />, { wrapper: environment().wrapper });
  await confirmEdit();
  fireEvent.click(screen.getByRole("button", { name: "保存して反映" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "質問を追加" })).toBeDisabled(),
  );
  await waitFor(() =>
    expect(
      screen
        .getAllByRole("alert")
        .some((item) => item.textContent?.includes("権限がありません")),
    ).toBe(true),
  );
  expect(
    screen.queryByRole("button", { name: "保存結果を再確認" }),
  ).not.toBeInTheDocument();
});
it("counts edits and movement independently while preserving question IDs", () => {
  const before = createBankFixture(3).questions;
  const after = [
    { ...before[1], question: "編集" },
    before[0],
    { ...before[2], id: storyIds.idempotency },
  ];
  expect(changeSummary(after, before)).toEqual({
    added: 1,
    removed: 1,
    edited: 1,
    moved: 2,
  });
});
it.each([
  "https://example.com/",
  "//example.com/",
  "/login/",
  "/admin/",
  "/practice/../login/",
])("restricts return URLs: %s", (value) => {
  expect(safeReturn(value)).toBe("/practice/");
});
it("does not send OTP on mount and blocks duplicate sends and early resend", async () => {
  const begin = vi.spyOn(auth, "begin").mockResolvedValue("challenge");
  const { result, unmount } = renderHook(useEmailOtpLogin, {
    wrapper: environment().wrapper,
  });
  expect(begin).not.toHaveBeenCalled();
  act(() => result.current.form.setValue("email", "user@example.invalid"));
  await act(async () => {
    await Promise.all([
      result.current.actions.submit(),
      result.current.actions.submit(),
    ]);
  });
  expect(begin).toHaveBeenCalledTimes(1);
  expect(result.current.view.cooldown).toBe(60);
  await act(async () => {
    await result.current.actions.resend();
  });
  expect(begin).toHaveBeenCalledTimes(1);
  unmount();
});
it("enables OTP resend after 60 ticks and removes the cooldown on unmount", async () => {
  vi.useFakeTimers();
  const begin = vi.spyOn(auth, "begin").mockResolvedValue("challenge");
  const { result, unmount } = renderHook(useEmailOtpLogin, {
    wrapper: environment().wrapper,
  });
  act(() => result.current.form.setValue("email", "user@example.invalid"));
  await act(async () => {
    await result.current.actions.submit();
  });
  for (let i = 0; i < 60; i++)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
  expect(result.current.view.cooldown).toBe(0);
  await act(async () => {
    await result.current.actions.resend();
  });
  expect(begin).toHaveBeenCalledTimes(2);
  unmount();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(61000);
  });
  expect(begin).toHaveBeenCalledTimes(2);
});
it("checks six digits and returns to the permitted screen after OTP success", async () => {
  vi.spyOn(auth, "begin").mockResolvedValue("challenge");
  const complete = vi.spyOn(auth, "complete").mockResolvedValue();
  const { result } = renderHook(useEmailOtpLogin, {
    wrapper: environment().wrapper,
  });
  act(() => result.current.form.setValue("email", "admin@example.invalid"));
  await act(async () => {
    await result.current.actions.submit();
  });
  act(() => result.current.form.setValue("code", "123"));
  await act(async () => {
    await result.current.actions.submit();
  });
  expect(complete).not.toHaveBeenCalled();
  act(() => result.current.form.setValue("code", "123456"));
  await act(async () => {
    await result.current.actions.submit();
  });
  expect(complete).toHaveBeenCalledWith(
    "admin@example.invalid",
    "challenge",
    "123456",
  );
  expect(replace).toHaveBeenCalledWith("/admin/questions/");
});
it("cancels and clears the previous user's queries on an identity change", () => {
  const { client, wrapper } = environment();
  const clear = vi.spyOn(client, "clear");
  const cancel = vi.spyOn(client, "cancelQueries");
  renderHook(useAccountActions, { wrapper });
  client.setQueryData(["private"], "admin-only");
  act(() => auth.setMockActor("other-user", ["USER"]));
  expect(cancel).toHaveBeenCalledTimes(1);
  expect(clear).toHaveBeenCalledTimes(1);
  expect(client.getQueryData(["private"])).toBeUndefined();
});
it("navigates to a completed evaluation once across rerenders", async () => {
  auth.setMockActor("mock-user", ["USER"]);
  const seed = createCompletedState();
  repository.write(seed);
  const session = seed.sessions[storyIds.session];
  const { rerender } = renderHook(() => usePracticeController(session, null), {
    wrapper: environment().wrapper,
  });
  await waitFor(() =>
    expect(push).toHaveBeenCalledWith(
      `/result/?attemptId=${storyIds.currentAttempt}`,
    ),
  );
  rerender();
  expect(push).toHaveBeenCalledTimes(1);
});
it("does not expose SDK error payloads in the login view", async () => {
  vi.spyOn(auth, "begin").mockRejectedValue(
    new ApiError("INTERNAL_SERVER_ERROR", 500),
  );
  const { result } = renderHook(useEmailOtpLogin, {
    wrapper: environment().wrapper,
  });
  act(() => result.current.form.setValue("email", "user@example.invalid"));
  await act(async () => {
    await result.current.actions.submit();
  });
  await waitFor(() =>
    expect(result.current.view.error).toContain("コードを送信できませんでした"),
  );
});
