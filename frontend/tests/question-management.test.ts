/** @file question-management.test.ts @description 公開・本人分離・最終問・保存再送の統合契約。 */
import { afterAll, afterEach, beforeAll, expect, it, vi } from "vitest";
import { setupServer } from "msw/node";
import { createHandlers, type Scenario } from "@/mocks/handlers";
import { createRepository } from "@/mocks/store";
import { auth } from "@/lib/auth/session";
import { questions, legacyQuestions } from "@/mocks/data/questions";
import { getQuestionBank, saveQuestionBank } from "@/lib/api/admin";
import {
  createSession,
  getQuestion,
  submitAnswer,
  getEvaluation,
  nextQuestion,
  getPracticeOptions,
} from "@/lib/api/interview";
import { bankSaveSchema, createSchema } from "@/lib/api/schemas";
import { save, readSaved, operationSchema } from "@/lib/storage/recovery";
import versionCases from "../../contracts/question-bank-version-fixtures.json";
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
  sessionStorage.clear();
});
afterAll(() => {
  server.close();
  vi.unstubAllEnvs();
});
it.each(versionCases)(
  "shares expectedVersion JSON semantics: $label",
  (testCase) => {
    const result = bankSaveSchema.safeParse({
      expectedVersion: JSON.parse(testCase.json),
      questions: [questions[0]],
    });
    expect(result.success).toBe(testCase.valid);
    if (result.success)
      expect(result.data.expectedVersion === testCase.value).toBe(true);
  },
);
it("shares 15 defaults and keeps legacy IDs separate", () => {
  expect(questions).toHaveLength(15);
  expect(legacyQuestions).toHaveLength(21);
  expect(questions[1].question).toContain("\nまた、その軸");
  expect(
    questions.every((q) => !legacyQuestions.some((old) => old.id === q.id)),
  ).toBe(true);
  expect(
    createSchema.safeParse({
      mode: "full",
      category: "career",
      difficulty: "standard",
    }).success,
  ).toBe(false);
  expect(
    bankSaveSchema.safeParse({ expectedVersion: 0, questions: [] }).success,
  ).toBe(false);
});
it("denies USER writes and requires ADMIN", async () => {
  await expect(getQuestionBank()).rejects.toMatchObject({ status: 403 });
  auth.setMockActor("admin", ["ADMIN"]);
  expect((await getQuestionBank()).version).toBe(0);
});
it("publishes edits only to new snapshots and replays a previous start", async () => {
  const key = crypto.randomUUID(),
    body = { mode: "full", difficulty: "standard" } as const;
  const before = await createSession(body, key);
  auth.setMockActor("admin", ["ADMIN"]);
  await saveQuestionBank(
    {
      expectedVersion: 0,
      questions: [{ ...questions[0], question: "編集した質問" }],
    },
    crypto.randomUUID(),
  );
  auth.setMockActor("mock-user", ["USER"]);
  expect((await getQuestion(before.sessionId)).question.question).toBe(
    questions[0].question,
  );
  expect(await createSession(body, key)).toEqual(before);
  const after = await createSession(body, crypto.randomUUID());
  expect((await getQuestion(after.sessionId)).question.question).toBe(
    "編集した質問",
  );
  expect((await getPracticeOptions()).totalQuestions).toBe(1);
});
it("finishes one-question practice, permits retry, and hides another owner's session", async () => {
  const { sessionId } = await createSession("career", crypto.randomUUID());
  const session = await getQuestion(sessionId);
  const body = { questionId: session.question.id, answer: "回答" };
  const accepted = await submitAnswer(sessionId, body, crypto.randomUUID());
  for (let i = 0; i < 3; i++) await getEvaluation(accepted.evaluationId);
  expect(session.hasNext).toBe(false);
  await expect(
    nextQuestion(sessionId, accepted.attemptId, crypto.randomUUID()),
  ).rejects.toMatchObject({ code: "SESSION_COMPLETED" });
  expect(
    (await submitAnswer(sessionId, body, crypto.randomUUID())).status,
  ).toBe("processing");
  auth.setMockActor("another-user", ["USER"]);
  await expect(getQuestion(sessionId)).rejects.toMatchObject({ status: 404 });
});
it("confirms a saved request after response loss and later updates", async () => {
  auth.setMockActor("admin", ["ADMIN"]);
  const key = crypto.randomUUID(),
    body = { expectedVersion: 0, questions: [questions[0]] };
  scenario = "response_lost";
  await expect(saveQuestionBank(body, key)).rejects.toMatchObject({
    code: "NETWORK_ERROR",
  });
  const receipt = await saveQuestionBank(body, key);
  expect(receipt.version).toBe(1);
  scenario = "success";
  await saveQuestionBank(
    { expectedVersion: 1, questions: [questions[1]] },
    crypto.randomUUID(),
  );
  expect(await saveQuestionBank(body, key)).toEqual(receipt);
  await expect(
    saveQuestionBank({ ...body, questions: [questions[2]] }, key),
  ).rejects.toMatchObject({ code: "IDEMPOTENCY_CONFLICT" });
});
it("rejects a stale editor and retains zero-version no-change semantics", async () => {
  auth.setMockActor("admin", ["ADMIN"]);
  expect(
    (
      await saveQuestionBank(
        { expectedVersion: 0, questions },
        crypto.randomUUID(),
      )
    ).version,
  ).toBe(0);
  await saveQuestionBank(
    { expectedVersion: 0, questions: [questions[0]] },
    crypto.randomUUID(),
  );
  auth.setMockActor("second-admin", ["ADMIN"]);
  await expect(
    saveQuestionBank(
      { expectedVersion: 0, questions: [questions[1]] },
      crypto.randomUUID(),
    ),
  ).rejects.toMatchObject({ code: "QUESTION_BANK_CONFLICT" });
});
it("isolates recovery by subject", () => {
  const value = {
    version: 1 as const,
    key: crypto.randomUUID(),
    category: "career" as const,
  };
  save("pocket:create", value);
  auth.setMockActor("other", ["USER"]);
  expect(readSaved("pocket:create", operationSchema)).toBeNull();
  auth.setMockActor("mock-user", ["USER"]);
  expect(readSaved("pocket:create", operationSchema)).toEqual(value);
});
