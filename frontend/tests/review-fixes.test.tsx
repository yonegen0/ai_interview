/** @file review-fixes.test.tsx @description 利用者切替・遅延応答・保存失敗・版復旧・旧要求移行の回帰試験。 */
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
import { z } from "zod";
import { auth } from "@/lib/auth/session";
import { request } from "@/lib/api/client";
import { createHandlers } from "@/mocks/handlers";
import { createRepository } from "@/mocks/store";
import { legacyQuestions, questions } from "@/mocks/data/questions";
import { createSession, nextQuestion, submitAnswer } from "@/lib/api/interview";
import {
  operationSchema,
  readSaved,
  recoverySchema,
  recoveryForScope,
  removeSaved,
  resetRecoveryMemoryForTests,
  save,
} from "@/lib/storage/recovery";
import { usePracticeStart } from "@/features/interview/hooks/usePracticeStart";
import { useFeedbackNavigation } from "@/features/feedback/hooks/useFeedbackNavigation";
import { useAnswer } from "@/features/interview/hooks/useAnswer";
import { useQuestionManagement } from "@/features/admin/hooks/useQuestionManagement";
import { QuestionManagement } from "@/features/admin/components/pages/QuestionManagement";
import { savedBankSchema, storageKey } from "@/features/admin/model/editor";
import { createCompletedState, storyIds } from "../stories/fixtures";
import { theme } from "@/theme/theme";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { PracticeStart } from "@/features/interview/components/pages/PracticeStart";
import { usePracticeController } from "@/features/interview/hooks/usePracticeController";
import { useAccountActions } from "@/hooks/useAccountActions";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/practice/",
  useSearchParams: () => new URLSearchParams(),
}));
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
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const options = {
  bankVersion: 0,
  totalQuestions: 1,
  categories: [
    { id: "self_introduction", label: "自己紹介", questionCount: 1 },
  ],
};
const bank = { version: 0, updatedAt: null, questions: [questions[0]] };
const updatedBank = {
  version: 1,
  updatedAt: "2026-10-06T00:00:00.000Z",
  questions: [{ ...questions[0], question: "保存した新しい質問です。" }],
};
beforeAll(() => vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost/api"));
beforeEach(() => {
  sessionStorage.clear();
  resetRecoveryMemoryForTests();
  auth.setMockActor("review-a", ["ADMIN"]);
});
afterEach(() => {
  for (const client of clients.splice(0)) {
    void client.cancelQueries();
    client.clear();
  }
  vi.restoreAllMocks();
  sessionStorage.clear();
  resetRecoveryMemoryForTests();
  push.mockClear();
});
afterAll(() => vi.unstubAllEnvs());

it.each(["review-b", "review-a"])(
  "does not resend a delayed 401 after a new login as %s",
  async (sub) => {
    const first = deferred<Response>();
    const send = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => first.promise);
    const pending = request("/admin/question-bank", z.unknown(), {
      method: "POST",
      key: crypto.randomUUID(),
      body: { expectedVersion: 0, questions: updatedBank.questions },
    });
    const rejected = expect(pending).rejects.toMatchObject({
      code: "UNAUTHORIZED",
      status: 401,
    });
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    await auth.logout();
    auth.setMockActor(sub, ["ADMIN"]);
    first.resolve(json({}, 401));
    await rejected;
    expect(send).toHaveBeenCalledTimes(1);
    expect(auth.snapshot()).toMatchObject({ phase: "authenticated", sub });
  },
);
it("does not invalidate a new login when the second 401 arrives", async () => {
  const second = deferred<Response>();
  const send = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(json({}, 401))
    .mockImplementationOnce(() => second.promise);
  const pending = request("/practice-options", z.unknown());
  const rejected = expect(pending).rejects.toMatchObject({
    code: "UNAUTHORIZED",
  });
  await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
  await auth.logout();
  auth.setMockActor("review-b", ["USER"]);
  second.resolve(json({}, 401));
  await rejected;
  expect(auth.snapshot()).toMatchObject({
    phase: "authenticated",
    sub: "review-b",
  });
});
it("rejects a successful body that finishes parsing after the login changes", async () => {
  const body = deferred<unknown>();
  const response = json({ ok: true });
  const parse = vi
    .spyOn(response, "json")
    .mockImplementation(() => body.promise);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
  const pending = request("/practice-options", z.object({ ok: z.boolean() }));
  const rejected = expect(pending).rejects.toMatchObject({
    code: "UNAUTHORIZED",
  });
  await waitFor(() => expect(parse).toHaveBeenCalledTimes(1));
  auth.setMockActor("review-b", ["USER"]);
  body.resolve({ ok: true });
  await rejected;
});
it("reconfirms a 401 with the same key and captured body for the same login", async () => {
  const first = deferred<Response>();
  const send = vi
    .spyOn(globalThis, "fetch")
    .mockImplementationOnce(() => first.promise)
    .mockResolvedValueOnce(json({ ok: true }));
  const body = {
    expectedVersion: 0,
    questions: structuredClone(updatedBank.questions),
  };
  const key = crypto.randomUUID();
  const pending = request(
    "/admin/question-bank",
    z.object({ ok: z.boolean() }),
    { method: "POST", key, body },
  );
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  body.questions[0].question = "後から変更された本文";
  first.resolve(json({}, 401));
  await expect(pending).resolves.toEqual({ ok: true });
  expect(send).toHaveBeenCalledTimes(2);
  expect(send.mock.calls[1][1]?.body).toBe(send.mock.calls[0][1]?.body);
  for (const call of send.mock.calls)
    expect(call[1]?.headers).toMatchObject({ "Idempotency-Key": key });
});

it.each([false, true])(
  "retains a pending start after unmount (switch login: %s)",
  async (switchLogin) => {
    const reply = deferred<Response>();
    const send = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((_url, init) =>
        init?.method === "POST"
          ? reply.promise
          : Promise.resolve(json(options)),
      );
    const { result, unmount } = renderHook(usePracticeStart, {
      wrapper: environment().wrapper,
    });
    await waitFor(() => expect(result.current.view.canStart).toBe(true));
    const owner = auth.scope();
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.actions.start();
    });
    await waitFor(() =>
      expect(send.mock.calls.some((call) => call[1]?.method === "POST")).toBe(
        true,
      ),
    );
    const original = readSaved("pocket:create", operationSchema);
    unmount();
    if (switchLogin) {
      await auth.logout();
      auth.setMockActor("review-b", ["USER"]);
    }
    const current = switchLogin
      ? {
          version: 1,
          key: crypto.randomUUID(),
          body: { mode: "full", difficulty: "standard" },
        }
      : original;
    if (switchLogin) save("pocket:create", current);
    await act(async () => {
      reply.resolve(json({ sessionId: storyIds.session }, 201));
      await pending;
    });
    expect(readSaved("pocket:create", operationSchema)).toEqual(current);
    expect(readSaved("pocket:create", operationSchema, owner)).toEqual(
      original,
    );
    expect(push).not.toHaveBeenCalled();
  },
);
it("does not execute a queued mutation with a later login", async () => {
  const send = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(options));
  const { result, unmount } = renderHook(usePracticeStart, {
    wrapper: environment().wrapper,
  });
  await waitFor(() => expect(result.current.view.canStart).toBe(true));
  const before = send.mock.calls.length;
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.actions.start();
    auth.setMockActor("review-b", ["USER"]);
  });
  await act(async () => {
    await pending;
  });
  expect(
    send.mock.calls.slice(before).filter((call) => call[1]?.method === "POST"),
  ).toHaveLength(0);
  expect(push).not.toHaveBeenCalled();
  unmount();
});
it("keeps the protected form usable after a new login by the same user", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) =>
    Promise.resolve(
      init?.method === "POST"
        ? json({ sessionId: storyIds.session }, 201)
        : json(options),
    ),
  );
  const view = render(
    <AuthBoundary>
      <PracticeStart />
    </AuthBoundary>,
    { wrapper: environment().wrapper },
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "練習を始める" })).toBeEnabled(),
  );
  act(() => {
    void auth.logout();
    auth.setMockActor("review-a", ["ADMIN"]);
  });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "練習を始める" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "練習を始める" }));
  await waitFor(() =>
    expect(push).toHaveBeenCalledWith(
      `/practice/session/?sessionId=${storyIds.session}`,
    ),
  );
  view.unmount();
});
it("does not update navigation or session cache when a next request finishes after unmount", async () => {
  auth.setMockActor("mock-user", ["USER"]);
  const seed = createCompletedState();
  const session = seed.sessions[storyIds.session];
  const feedback = seed.attempts[storyIds.currentAttempt].feedback;
  const reply = deferred<Response>();
  const send = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation((_url, init) =>
      init?.method === "POST" ? reply.promise : Promise.resolve(json(session)),
    );
  const { client, wrapper } = environment();
  const { result, unmount } = renderHook(
    () => useFeedbackNavigation(feedback),
    { wrapper },
  );
  await waitFor(() => expect(result.current.view.canNext).toBe(true));
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.actions.next();
  });
  await waitFor(() =>
    expect(send.mock.calls.some((call) => call[1]?.method === "POST")).toBe(
      true,
    ),
  );
  const key = `pocket:next:${feedback.attemptId}`;
  const original = readSaved(key, operationSchema);
  unmount();
  await act(async () => {
    reply.resolve(json({ ...session, questionNumber: 2, activeAttempt: null }));
    await pending;
  });
  expect(
    client.getQueryData([auth.scope(), "session", session.sessionId]),
  ).toEqual(session);
  expect(readSaved(key, operationSchema)).toEqual(original);
  expect(push).not.toHaveBeenCalled();
});
it("retains the exact pending answer when acceptance arrives after unmount", async () => {
  const session = {
    ...createCompletedState().sessions[storyIds.session],
    activeAttempt: null,
  };
  const reply = deferred<Response>();
  const send = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(() => reply.promise);
  const { result, unmount } = renderHook(() => useAnswer(session, null), {
    wrapper: environment().wrapper,
  });
  let pending!: Promise<void>;
  act(() => {
    pending = result.current.send({ answer: "遅延応答でも保持する回答" });
  });
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  const key = `pocket:answer:${session.sessionId}`;
  const original = readSaved(key, recoverySchema);
  unmount();
  await act(async () => {
    reply.resolve(
      json(
        {
          attemptId: storyIds.currentAttempt,
          evaluationId: storyIds.evaluation,
          status: "processing",
        },
        202,
      ),
    );
    await pending;
  });
  expect(readSaved(key, recoverySchema)).toEqual(original);
  expect(original?.pending?.body.answer).toBe("遅延応答でも保持する回答");
});

it.each([false, true])(
  "restores the latest memory after quota (prior persisted value: %s)",
  (persisted) => {
    const schema = z.object({ text: z.string() });
    if (persisted) save("draft", { text: "古い本文" });
    const write = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new DOMException("quota", "QuotaExceededError");
      });
    expect(save("draft", { text: "最新の本文" })).toBe(false);
    expect(readSaved("draft", schema)).toEqual({ text: "最新の本文" });
    write.mockRestore();
    expect(save("draft", { text: "書込復旧後の本文" })).toBe(true);
    expect(readSaved("draft", schema)).toEqual({ text: "書込復旧後の本文" });
  },
);
it("does not resurrect deleted data when removeItem fails", () => {
  const schema = z.object({ text: z.string() });
  save("draft", { text: "削除した本文" });
  const remove = vi
    .spyOn(Storage.prototype, "removeItem")
    .mockImplementation(() => {
      throw new Error("unavailable");
    });
  removeSaved("draft");
  expect(readSaved("draft", schema)).toBeNull();
  remove.mockRestore();
  removeSaved("draft");
  expect(readSaved("draft", schema)).toBeNull();
});
it("keeps bound storage isolated when the current login changes", () => {
  const schema = z.object({ text: z.string() });
  const first = recoveryForScope(auth.scope());
  first.save("draft", { text: "Aの下書き" });
  auth.setMockActor("review-b", ["USER"]);
  save("draft", { text: "Bの下書き" });
  first.removeSaved("draft");
  expect(readSaved("draft", schema)).toEqual({ text: "Bの下書き" });
  expect(first.readSaved("draft", schema)).toBeNull();
});
it("keeps the latest mock bank and request receipts after write-only quota failure", () => {
  const repository = createRepository(true);
  repository.reset();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("quota", "QuotaExceededError");
  });
  const next = structuredClone(repository.read());
  next.bank = updatedBank;
  next.requests["review-a:key"] = {
    fingerprint: "saved request",
    status: 200,
    body: { version: 1 },
  };
  repository.write(next);
  expect(repository.read().bank).toEqual(updatedBank);
  expect(repository.read().requests["review-a:key"]).toEqual(
    next.requests["review-a:key"],
  );
});

it("waits for a fresh bank before comparing restored data with stale cache", async () => {
  save(storageKey, {
    baseline: updatedBank,
    draft: { expectedVersion: 1, questions: updatedBank.questions },
  });
  const { client, wrapper } = environment();
  const key = [auth.scope(), "admin-question-bank"];
  client.setQueryData(key, bank);
  const reply = deferred<Response>();
  const send = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(() => reply.promise);
  const { result, unmount } = renderHook(useQuestionManagement, { wrapper });
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  expect(result.current.view.initialized).toBe(false);
  expect(result.current.view.stage).toBe("editable");
  await act(async () => {
    reply.resolve(json(updatedBank));
  });
  await waitFor(() => expect(result.current.view.initialized).toBe(true));
  expect(result.current.view.stage).toBe("editable");
  expect(result.current.view.comparison).toBeNull();
  expect(result.current.view.questions).toEqual(updatedBank.questions);
  expect(result.current.view.disabled).toBe(false);
  unmount();
});
async function confirmEdit() {
  const input = (await screen.findAllByLabelText("質問本文"))[0];
  fireEvent.change(input, {
    target: { value: updatedBank.questions[0].question },
  });
  const confirm = screen.getByRole("button", { name: "保存内容を確認" });
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  await screen.findByRole("button", { name: "保存して反映" });
}
it("updates the bank cache after saving and remounts without a false conflict", async () => {
  let latest = bank as typeof bank | typeof updatedBank;
  vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => {
    if (init?.method === "POST") {
      latest = updatedBank;
      return Promise.resolve(
        json({
          version: 1,
          updatedAt: updatedBank.updatedAt,
          totalQuestions: 1,
        }),
      );
    }
    return Promise.resolve(json(latest));
  });
  const { client, wrapper } = environment();
  const first = render(<QuestionManagement />, { wrapper });
  await confirmEdit();
  fireEvent.click(screen.getByRole("button", { name: "保存して反映" }));
  await screen.findByText(/質問一覧を保存しました/);
  expect(client.getQueryData([auth.scope(), "admin-question-bank"])).toEqual(
    updatedBank,
  );
  first.unmount();
  const second = render(<QuestionManagement />, { wrapper });
  await waitFor(() => expect(screen.getByLabelText("質問本文")).toBeEnabled());
  expect(screen.getByLabelText("質問本文")).toHaveValue(
    updatedBank.questions[0].question,
  );
  expect(screen.queryByRole("heading", { name: "最新版との比較" })).toBeNull();
  second.unmount();
});
it("preserves another admin's draft and cache when a previous save settles after logout", async () => {
  const reply = deferred<Response>();
  const send = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation((_url, init) =>
      init?.method === "POST" ? reply.promise : Promise.resolve(json(bank)),
    );
  const { client, wrapper } = environment();
  const firstScope = auth.scope();
  const view = render(<QuestionManagement />, { wrapper });
  await confirmEdit();
  fireEvent.click(screen.getByRole("button", { name: "保存して反映" }));
  await waitFor(() =>
    expect(send.mock.calls.some((call) => call[1]?.method === "POST")).toBe(
      true,
    ),
  );
  const original = readSaved(storageKey, savedBankSchema);
  view.unmount();
  await auth.logout();
  auth.setMockActor("review-b", ["ADMIN"]);
  const current = {
    baseline: bank,
    draft: {
      expectedVersion: 0,
      questions: [{ ...questions[0], question: "Bの編集" }],
    },
  };
  save(storageKey, current);
  client.setQueryData([auth.scope(), "admin-question-bank"], bank);
  await act(async () => {
    reply.resolve(
      json({ version: 1, updatedAt: updatedBank.updatedAt, totalQuestions: 1 }),
    );
  });
  await waitFor(() => expect(client.isMutating()).toBe(0));
  expect(readSaved(storageKey, savedBankSchema)).toEqual(current);
  expect(readSaved(storageKey, savedBankSchema, firstScope)).toEqual(original);
  expect(client.getQueryData([auth.scope(), "admin-question-bank"])).toEqual(
    bank,
  );
});

it.each(["start", "answer", "next"] as const)(
  "replays a legacy %s receipt without executing it again",
  async (operation) => {
    auth.setMockActor("mock-user", ["USER"]);
    const id = "10000000-0000-4000-8000-000000000099";
    const key = crypto.randomUUID();
    const session = {
      sessionId: id,
      question: legacyQuestions[0],
      questionNumber: 4,
      activeAttempt: null,
    };
    const body =
      operation === "start"
        ? { category: "job_change", difficulty: "standard" }
        : operation === "answer"
          ? { questionId: session.question.id, answer: "保存済み回答" }
          : { fromAttemptId: storyIds.currentAttempt };
    const path =
      operation === "start"
        ? "/api/sessions"
        : `/api/sessions/${id}/${operation === "answer" ? "answers" : "questions/next"}`;
    const receipt =
      operation === "start"
        ? { sessionId: id }
        : operation === "answer"
          ? {
              attemptId: storyIds.currentAttempt,
              evaluationId: storyIds.evaluation,
              status: "processing",
            }
          : session;
    const old = {
      version: 1,
      sessions: { [id]: session },
      attempts: {},
      requests: {
        [key]: {
          fingerprint: `${path}:${JSON.stringify(body)}`,
          status:
            operation === "start" ? 201 : operation === "answer" ? 202 : 200,
          body: receipt,
        },
      },
      consumed: [],
    };
    const raw = JSON.stringify(old);
    sessionStorage.setItem("pocket:mock:v1", raw);
    const repository = createRepository(true);
    const server = setupServer(
      ...createHandlers(repository, () => "success", "http://localhost/api"),
    );
    server.listen({ onUnhandledRequest: "error" });
    try {
      const value =
        operation === "start"
          ? await createSession("job_change", key)
          : operation === "answer"
            ? await submitAnswer(
                id,
                { questionId: session.question.id, answer: "保存済み回答" },
                key,
              )
            : await nextQuestion(id, storyIds.currentAttempt, key);
      expect(value).toEqual(receipt);
      expect(Object.keys(repository.read().sessions)).toHaveLength(1);
      expect(Object.keys(repository.read().attempts)).toHaveLength(0);
      expect(sessionStorage.getItem("pocket:mock:v1")).toBe(raw);
    } finally {
      server.close();
    }
  },
);
it("repairs unscoped receipts in an already migrated v2 store without replacing scoped receipts", () => {
  const repository = createRepository(true);
  const state = repository.read();
  const key = crypto.randomUUID();
  const receipt = {
    fingerprint: "legacy request",
    status: 201,
    body: { sessionId: storyIds.session },
  };
  state.requests[key] = receipt;
  sessionStorage.setItem("pocket:mock:v2", JSON.stringify(state));
  expect(repository.read().requests[`mock-user:${key}`]).toEqual(receipt);
  const current = { ...receipt, fingerprint: "already scoped request" };
  state.requests[`mock-user:${key}`] = current;
  sessionStorage.setItem("pocket:mock:v2", JSON.stringify(state));
  expect(repository.read().requests[`mock-user:${key}`]).toEqual(current);
});

it.each(["unmount", "switch", "relogin"] as const)(
  "ignores a delayed evaluation and stale exit after %s",
  async (change) => {
    const seed = createCompletedState();
    const session = seed.sessions[storyIds.session];
    const evaluation = seed.attempts[storyIds.currentAttempt].evaluation;
    const reply = deferred<Response>();
    const send = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => reply.promise);
    const { client, wrapper } = environment();
    const { result, unmount } = renderHook(
      () => usePracticeController(session, null),
      { wrapper },
    );
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    const staleExit = result.current.actions.exit;
    if (change === "unmount") unmount();
    else {
      await act(async () => {
        await auth.logout();
        auth.setMockActor(change === "switch" ? "review-b" : "review-a", [
          "USER",
        ]);
      });
    }
    const key = `pocket:answer:${session.sessionId}`;
    const draft = {
      version: 1,
      questionId: session.question.id,
      context: `${session.questionNumber}:normal`,
      draft: "現在のログインの下書き",
    };
    save(key, draft);
    await act(async () => {
      reply.resolve(json(evaluation));
      await reply.promise;
    });
    await waitFor(() => expect(client.isFetching()).toBe(0));
    act(() => staleExit());
    expect(push).not.toHaveBeenCalled();
    expect(readSaved(key, recoverySchema)).toEqual(draft);
    if (change !== "unmount") unmount();
  },
);

it.each(["review-b", "review-a"])(
  "preserves queries started by the new login as %s after cache cleanup",
  async (sub) => {
    const { client, wrapper } = environment();
    const { unmount } = renderHook(useAccountActions, { wrapper });
    const previousKey = [auth.scope(), "private"];
    client.setQueryData(previousKey, "old login");
    let currentKey!: (string | null)[];
    act(() => {
      auth.setMockActor(sub, ["USER"]);
      currentKey = [auth.scope(), "practice-options"];
      client.setQueryData(currentKey, options);
    });
    expect(client.getQueryData(previousKey)).toBeUndefined();
    expect(client.getQueryData(currentKey)).toEqual(options);
    await expect(
      client.fetchQuery({ queryKey: currentKey, queryFn: async () => options }),
    ).resolves.toEqual(options);
    expect(client.getQueryData(currentKey)).toEqual(options);
    unmount();
  },
);
