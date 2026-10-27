/** @file star-workspace-audit.test.tsx @description Delayed draft hydration preserves edits and restores preferences. */
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { setupServer } from "msw/node";
import { createHandlers } from "@/mocks/handlers";
import { createRepository } from "@/mocks/store";
import { startStarJob, fakeStarResult, finishStarJob } from "@/mocks/star";
import { createSession, getQuestion } from "@/lib/api/interview";
import * as starApi from "@/lib/api/star";
import { auth } from "@/lib/auth/session";
import { useStarWorkspace } from "@/features/starAssist/hooks/useStarWorkspace";
import {
  contextReceiptSchema,
  preferencesReceiptSchema,
  starReceiptSchema,
  emptyStarInput,
  type Drafts,
  type StarOperation,
} from "@/lib/api/schemas/star";

const repository = createRepository();
const server = setupServer(...createHandlers(repository));
const clients: QueryClient[] = [];
beforeEach(() => {
  sessionStorage.clear();
  auth.setMockActor("workspace-audit", ["USER"]);
  repository.reset();
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => {
  vi.restoreAllMocks();
  for (const client of clients.splice(0)) client.clear();
  server.close();
});
function operation(
  path: string,
  body: unknown,
  method: "POST" | "PUT" = "POST",
): StarOperation {
  return {
    version: 1,
    key: crypto.randomUUID(),
    path,
    body,
    method,
    contextId: null,
    editGeneration: 0,
  };
}
async function setup(saved: boolean) {
  const created = await createSession(
    { mode: "category", category: "job_change", difficulty: "standard" },
    crypto.randomUUID(),
  );
  const session = await getQuestion(created.sessionId);
  const origin = {
    operationKind: "initial_answer" as const,
    questionId: session.question.id,
  };
  const context = await starApi.executeStarOperation(
    operation(`/sessions/${session.sessionId}/answer-contexts`, origin),
    contextReceiptSchema,
  );
  if (saved)
    await starApi.executeStarOperation(
      operation(`/answer-contexts/${context.contextId}/star-drafts`, {
        ...emptyStarInput(),
        targetCategory: "corporate_sales",
        notes: { S: "", T: "", A: "保存された旧メモ", R: "" },
      }),
      starReceiptSchema,
    );
  await starApi.executeStarOperation(
    operation(
      "/star-assist/preferences",
      {
        category: {
          expectedVersion: 0,
          expectedGeneration: null,
          targetCategory: "it_engineering",
        },
      },
      "PUT",
    ),
    preferencesReceiptSchema,
  );
  const snapshot = await starApi.getDrafts(context.contextId);
  let resolve!: (value: Drafts) => void;
  const delayed = new Promise<Drafts>((done) => {
    resolve = done;
  });
  const get = vi.spyOn(starApi, "getDrafts").mockReturnValue(delayed);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const restore = vi.fn();
  const hook = renderHook(
    () => useStarWorkspace(session, origin, "", false, true, null, restore),
    { wrapper },
  );
  await waitFor(() => expect(get).toHaveBeenCalled());
  await waitFor(() =>
    expect(
      client.getQueryData([auth.scope(), "star-preferences"]),
    ).toBeDefined(),
  );
  return {
    ...hook,
    contextId: context.contextId,
    resolve: () => {
      get.mockRestore();
      resolve(snapshot);
    },
  };
}
it("does not replace STAR input typed before a delayed saved draft arrives", async () => {
  const hook = await setup(true);
  act(() =>
    hook.result.current.form.setValue(
      "notes.A",
      "読み込み中に本人が入力した新メモ",
      { shouldDirty: true },
    ),
  );
  await act(async () => hook.resolve());
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  expect(hook.result.current.form.getValues("notes.A")).toBe(
    "読み込み中に本人が入力した新メモ",
  );
  expect(hook.result.current.status).toBe("競合");
});
it("restores preferences received before the initial empty draft response", async () => {
  const hook = await setup(false);
  await act(async () => hook.resolve());
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  await waitFor(() =>
    expect(hook.result.current.input.targetCategory).toBe("it_engineering"),
  );
});
it("saves STAR edits typed before an empty draft response instead of marking them saved", async () => {
  const hook = await setup(false);
  act(() =>
    hook.result.current.form.setValue(
      "notes.A",
      "初回読込中に入力した未保存メモ",
      { shouldDirty: true },
    ),
  );
  await act(async () => hook.resolve());
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  await waitFor(
    () => expect(Object.values(repository.read().star.drafts)).toHaveLength(1),
    { timeout: 4000 },
  );
  expect((await starApi.getDrafts(hook.contextId)).starDraft?.notes.A).toBe(
    "初回読込中に入力した未保存メモ",
  );
});

it("does not auto-adopt a generation when input changes during the preceding save", async () => {
  const hook = await setup(false);
  await act(async () => hook.resolve());
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  act(() => {
    hook.result.current.form.setValue("targetCategory", "corporate_sales", {
      shouldDirty: true,
    });
    hook.result.current.form.setValue("notes.A", "生成時の元の行動", {
      shouldDirty: true,
    });
  });
  let release!: () => void;
  const blocked = new Promise<void>((done) => {
    release = done;
  });
  let captured!: () => void;
  const started = new Promise<void>((done) => {
    captured = done;
  });
  const original = starApi.executeStarOperation;
  const spy = vi.spyOn(starApi, "executeStarOperation").mockImplementation(
    async (operation, schema) => {
      if (operation.path.includes("/star-drafts") &&
          operation.method === "POST") {
        captured();
        await blocked;
      }
      return original(operation, schema);
    },
  );
  let generating!: Promise<void>;
  act(() => {
    generating = hook.result.current.generate();
  });
  await started;
  act(() => {
    hook.result.current.form.setValue("notes.A", "保存待ち中に書き換えた行動", {
      shouldDirty: true,
    });
  });
  await act(async () => {
    release();
    await generating;
  });
  spy.mockRestore();
  await waitFor(() => expect(hook.result.current.generating).toBe(true));

  const state = repository.read();
  const ids = Object.keys(state.star.generations);
  expect(ids).toHaveLength(1);
  const lease = startStarJob(state, ids[0], Date.now());
  expect(lease).not.toBeNull();
  finishStarJob(state, lease!, fakeStarResult(lease!), Date.now());
  repository.write(state);
  await act(async () => {
    await new Promise((done) => setTimeout(done, 1150));
  });
  await waitFor(() => expect(hook.result.current.resultWaiting).toBe(true));
  expect(hook.result.current.form.getValues("notes.A")).toBe(
    "保存待ち中に書き換えた行動",
  );
  expect(hook.result.current.form.getValues("candidates")).toHaveLength(0);
});
