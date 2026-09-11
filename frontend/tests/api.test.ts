/** @file api.test.ts @description 実API Clientを通したMSW契約と冪等性 */
import { afterAll, afterEach, beforeAll, expect, it, vi } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { z } from "zod";
import { createRepository } from "@/mocks/store";
import { createHandlers, type Scenario } from "@/mocks/handlers";
import {
  createSession,
  getQuestion,
  submitAnswer,
  getEvaluation,
  nextQuestion,
} from "@/lib/api/interview";
import { getFeedback } from "@/lib/api/feedback";
import { request } from "@/lib/api/client";
const repository = createRepository();
let scenario: Scenario = "success";
const server = setupServer(
  ...createHandlers(repository, () => scenario, "http://localhost/api"),
);
beforeAll(() => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost/api");
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => {
  repository.reset();
  scenario = "success";
  server.resetHandlers();
});
afterAll(() => {
  server.close();
  vi.unstubAllEnvs();
});
const start = async () => {
  const created = await createSession("career", crypto.randomUUID());
  return getQuestion(created.sessionId);
};
it("runs session, answer, three polls, feedback, retry and next", async () => {
  const session = await start();
  const key = crypto.randomUUID();
  const body = {
    questionId: session.question.id,
    answer: "学び続けたいです。",
  };
  const attempt = await submitAnswer(session.sessionId, body, key);
  expect(await submitAnswer(session.sessionId, body, key)).toEqual(attempt);
  await expect(
    submitAnswer(session.sessionId, { ...body, answer: "変更" }, key),
  ).rejects.toMatchObject({ code: "IDEMPOTENCY_CONFLICT" });
  expect((await getEvaluation(attempt.evaluationId)).status).toBe("processing");
  expect((await getEvaluation(attempt.evaluationId)).status).toBe("processing");
  expect((await getEvaluation(attempt.evaluationId)).status).toBe("completed");
  expect((await getFeedback(attempt.attemptId)).answer).toBe(body.answer);
  const nextKey = crypto.randomUUID();
  const next = await nextQuestion(
    session.sessionId,
    attempt.attemptId,
    nextKey,
  );
  expect(next.questionNumber).toBe(2);
  expect(next.question.id).not.toBe(session.question.id);
  expect(
    await nextQuestion(session.sessionId, attempt.attemptId, nextKey),
  ).toEqual(next);
  await expect(
    nextQuestion(session.sessionId, attempt.attemptId, crypto.randomUUID()),
  ).rejects.toMatchObject({ code: "SESSION_STATE_CONFLICT" });
});
it("deduplicates an answer after response loss", async () => {
  const session = await start();
  scenario = "response_lost";
  const key = crypto.randomUUID();
  const body = { questionId: session.question.id, answer: "回答" };
  await expect(
    submitAnswer(session.sessionId, body, key),
  ).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  await submitAnswer(session.sessionId, body, key);
  expect(Object.keys(repository.read().attempts)).toHaveLength(1);
});
it("creates a new attempt only after confirmed failure", async () => {
  const session = await start();
  scenario = "evaluation_failed";
  const body = { questionId: session.question.id, answer: "回答" };
  const first = await submitAnswer(
    session.sessionId,
    body,
    crypto.randomUUID(),
  );
  for (let i = 0; i < 3; i++) await getEvaluation(first.evaluationId);
  const second = await submitAnswer(
    session.sessionId,
    body,
    crypto.randomUUID(),
  );
  expect(second.attemptId).not.toBe(first.attemptId);
});
it("maps malformed responses", async () => {
  server.use(
    http.get("http://localhost/api/bad", () =>
      HttpResponse.json({ wrong: true }),
    ),
  );
  await expect(
    request("/bad", z.object({ id: z.string() })),
  ).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
});
it("distinguishes timeout and caller abort", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(
    (_input, init) =>
      new Promise((_resolve, reject) => {
        const abort = () => reject(new DOMException("Aborted", "AbortError"));
        if (init?.signal?.aborted) abort();
        else init?.signal?.addEventListener("abort", abort);
      }),
  );
  await expect(
    request("/wait", z.unknown(), { timeout: 10 }),
  ).rejects.toMatchObject({ code: "TIMEOUT" });
  const controller = new AbortController();
  controller.abort();
  await expect(
    request("/wait", z.unknown(), { signal: controller.signal }),
  ).rejects.toMatchObject({ code: "ABORTED" });
  spy.mockRestore();
});
