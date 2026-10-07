/** @file coaching-v2.test.ts @description V2 contracts, authoritative history, retry, and replay through the API client. */
import { afterAll, afterEach, beforeAll, expect, it, vi } from "vitest";
import { setupServer } from "msw/node";
import corpus from "../../contracts/coaching-v2-fixtures.json";
import { createHandlers, type Scenario } from "@/mocks/handlers";
import { createRepository } from "@/mocks/store";
import {
  createSession,
  getQuestion,
  submitAnswer,
  getEvaluation,
  nextQuestion,
} from "@/lib/api/interview";
import { getFeedback } from "@/lib/api/feedback";
import {
  submitSchema,
  feedbackSchema,
  coachingAnswerSchema,
  coachingResultSchema,
  bankSaveSchemaForBaseline,
  type Attempt,
  type FeedbackV2,
  sessionSchema,
} from "@/lib/api/schemas";
import {
  countCodePoints,
  countLegacyAnswerUnits,
  scoreValues,
} from "@/lib/textLimits";
import { auth } from "@/lib/auth/session";
import { questions } from "@/mocks/data/questions";
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
  scenario = "success";
  repository.reset();
  sessionStorage.clear();
});
afterAll(() => {
  server.close();
  vi.unstubAllEnvs();
});
async function start(answer = "顧客の相談に対応しました。") {
  const { sessionId } = await createSession(
    { mode: "full", difficulty: "standard" },
    crypto.randomUUID(),
  );
  const session = await getQuestion(sessionId);
  const body = {
    kind: "initial_answer" as const,
    questionId: session.question.id,
    answer,
  };
  const key = crypto.randomUUID();
  const accepted = await submitAnswer(sessionId, body, key);
  return { sessionId, session, body, key, accepted };
}
async function finish(accepted: Attempt): Promise<FeedbackV2> {
  for (let i = 0; i < 3; i++) await getEvaluation(accepted.evaluationId);
  return getFeedback(
    accepted.attemptId,
    undefined,
    accepted.evaluationId,
  ) as Promise<FeedbackV2>;
}
it.each(corpus.unicode)(
  "counts shared Unicode fixture $name without changing raw text",
  (fixture) => {
    const { codePoints, utf16 } = fixture;
    const text: string = fixture.textJson
      ? JSON.parse(fixture.textJson)
      : fixture.text;
    expect(countCodePoints(text)).toBe(codePoints);
    expect(countLegacyAnswerUnits(text)).toBe(utf16);
    expect(JSON.parse(JSON.stringify(text))).toBe(text);
  },
);
it.each([null, "", "unknown", false])(
  "never falls back for present kind %s",
  (kind) => {
    expect(
      submitSchema.safeParse({
        kind,
        questionId: questions[0].id,
        answer: "回答",
      }).success,
    ).toBe(false);
  },
);
it.each([399, 400, 401])("validates V2 code point boundary %i", (n) => {
  expect(coachingAnswerSchema.safeParse("🙂".repeat(n)).success).toBe(n <= 400);
});
it("retains all discriminator fields and rejects answer on evaluation retry", () => {
  const id = crypto.randomUUID();
  for (const body of [
    {
      kind: "coaching_answer",
      questionId: id,
      answer: "はい",
      attemptId: id,
      fromEvaluationId: id,
    },
    {
      kind: "retry_attempt",
      questionId: id,
      answer: "回答",
      fromAttemptId: id,
      fromEvaluationId: id,
    },
    { kind: "retry_evaluation", attemptId: id, fromEvaluationId: id },
  ])
    expect(submitSchema.parse(body)).toEqual(body);
  expect(
    submitSchema.safeParse({
      kind: "retry_evaluation",
      attemptId: id,
      fromEvaluationId: id,
      answer: "勝手な変更",
    }).success,
  ).toBe(false);
  expect(
    feedbackSchema.safeParse({ feedbackVersion: 3, score: 78 }).success,
  ).toBe(false);
});
it("completes three accepted follow-ups, preserves past rounds, rejects stale operations atomically", async () => {
  scenario = "coaching_max";
  const {
    sessionId,
    session,
    body,
    key,
    accepted: initial,
  } = await start("🙂".repeat(400));
  let accepted = initial;
  const evaluations: string[] = [];
  for (let round = 0; round <= 3; round++) {
    const feedback = await finish(accepted);
    evaluations.push(accepted.evaluationId);
    expect(feedback.coachingCount).toBe(round);
    expect(feedback.lengthPenalty).toBe(2);
    expect(feedback.result.status).toBe(round === 3 ? "completed" : "coaching");
    if (round === 3) break;
    const payload = {
      kind: "coaching_answer" as const,
      attemptId: accepted.attemptId,
      fromEvaluationId: accepted.evaluationId,
      questionId: session.question.id,
      answer: round ? "自分で確認しました。" : "分からない",
    };
    const sendKey = crypto.randomUUID();
    accepted = await submitAnswer(sessionId, payload, sendKey);
    const before = structuredClone(repository.read());
    expect(await submitAnswer(sessionId, payload, sendKey)).toEqual(accepted);
    expect(repository.read()).toEqual(before);
    await expect(
      submitAnswer(sessionId, payload, crypto.randomUUID()),
    ).rejects.toMatchObject({ status: 409 });
    expect(repository.read()).toEqual(before);
  }
  const before = structuredClone(repository.read());
  expect(await submitAnswer(sessionId, body, key)).toEqual(initial);
  expect(
    repository.read().attempts[initial.attemptId].initialEvaluationId,
  ).toBe(initial.evaluationId);
  expect(repository.read()).toEqual(before);
  expect(
    (
      (await getFeedback(
        initial.attemptId,
        undefined,
        evaluations[0],
      )) as FeedbackV2
    ).coachingCount,
  ).toBe(0);
  await getEvaluation(evaluations[0]);
  expect(repository.read()).toEqual(before);
  const retried = await submitAnswer(
    sessionId,
    {
      kind: "retry_attempt",
      questionId: session.question.id,
      answer: "新しい回答です。",
      fromAttemptId: accepted.attemptId,
      fromEvaluationId: accepted.evaluationId,
    },
    crypto.randomUUID(),
  );
  expect(retried.attemptId).not.toBe(initial.attemptId);
  scenario = "success";
  expect((await finish(retried)).coachingHistory).toEqual([]);
  expect(
    (await nextQuestion(sessionId, retried.attemptId, crypto.randomUUID()))
      .questionNumber,
  ).toBe(2);
});
it("keeps failed history through reload and retries only the fixed input", async () => {
  scenario = "coaching";
  const { sessionId, session, accepted } = await start();
  await finish(accepted);
  const failed = await submitAnswer(
    sessionId,
    {
      kind: "coaching_answer",
      questionId: session.question.id,
      attemptId: accepted.attemptId,
      fromEvaluationId: accepted.evaluationId,
      answer: "いいえ。上司の提案です。",
    },
    crypto.randomUUID(),
  );
  scenario = "evaluation_failed";
  for (let i = 0; i < 3; i++) await getEvaluation(failed.evaluationId);
  expect((await getQuestion(sessionId)).activeCoaching).toMatchObject({
    stage: "failed",
    coachingCount: 1,
    latestAnswer: "いいえ。上司の提案です。",
    lastSuccessfulEvaluationId: accepted.evaluationId,
  });
  const before = structuredClone(repository.read());
  for (const payload of [
    { questionId: session.question.id, answer: "リセット" },
    {
      kind: "initial_answer" as const,
      questionId: session.question.id,
      answer: "リセット",
    },
  ]) {
    await expect(
      submitAnswer(sessionId, payload, crypto.randomUUID()),
    ).rejects.toMatchObject({ status: 409 });
    expect(repository.read()).toEqual(before);
  }
  await expect(getFeedback(failed.attemptId)).rejects.toMatchObject({
    status: 409,
  });
  const retry = await submitAnswer(
    sessionId,
    {
      kind: "retry_evaluation",
      attemptId: failed.attemptId,
      fromEvaluationId: failed.evaluationId,
    },
    crypto.randomUUID(),
  );
  expect(repository.read().evaluations[retry.evaluationId].input).toEqual(
    before.evaluations[failed.evaluationId].input,
  );
  expect(
    repository.read().evaluations[failed.evaluationId].evaluation.status,
  ).toBe("failed");
  scenario = "success";
  expect((await finish(retry)).coachingHistory).toHaveLength(1);
});
it("denies other owners and concurrent accepts without partial records", async () => {
  scenario = "coaching";
  const { sessionId, session, accepted } = await start();
  await finish(accepted);
  const payload = {
    kind: "coaching_answer" as const,
    attemptId: accepted.attemptId,
    fromEvaluationId: accepted.evaluationId,
    questionId: session.question.id,
    answer: "確認しました。",
  };
  const replies = await Promise.allSettled([
    submitAnswer(sessionId, payload, crypto.randomUUID()),
    submitAnswer(sessionId, payload, crypto.randomUUID()),
  ]);
  expect(replies.filter((r) => r.status === "fulfilled")).toHaveLength(1);
  expect(repository.read().coachings[accepted.attemptId].coachingCount).toBe(1);
  const before = structuredClone(repository.read());
  auth.setMockActor("other-owner", ["USER"]);
  await expect(
    getFeedback(accepted.attemptId, undefined, accepted.evaluationId),
  ).rejects.toMatchObject({ status: 404 });
  await expect(
    submitAnswer(sessionId, payload, crypto.randomUUID()),
  ).rejects.toMatchObject({ status: 404 });
  expect(repository.read()).toEqual(before);
});
it("validates changed questions while preserving exact historical text and category changes", () => {
  const old = { ...questions[0], question: "字".repeat(250) };
  const schema = bankSaveSchemaForBaseline([old]);
  expect(
    schema.safeParse({
      expectedVersion: 1,
      questions: [old, { ...questions[1], question: "🙂".repeat(200) }],
    }).success,
  ).toBe(true);
  expect(
    schema.safeParse({
      expectedVersion: 1,
      questions: [{ ...old, category: "career" }],
    }).success,
  ).toBe(true);
  for (const changed of [
    { ...old, question: "字".repeat(201) },
    { ...old, id: crypto.randomUUID() },
    { ...old, question: old.question + " " },
  ])
    expect(
      schema.safeParse({ expectedVersion: 1, questions: [changed] }).success,
    ).toBe(false);
});
it("marks the same unavailable answer variants as Backend in fixed inputs", async () => {
  scenario = "coaching";
  for (const answer of ["分かりません", "思いつきません", "覚えていません。"]) {
    const { sessionId, session, accepted } = await start();
    const previous = await finish(accepted);
    const next = await submitAnswer(
      sessionId,
      {
        kind: "coaching_answer",
        questionId: session.question.id,
        attemptId: accepted.attemptId,
        fromEvaluationId: accepted.evaluationId,
        answer,
      },
      crypto.randomUUID(),
    );
    expect(
      repository.read().evaluations[next.evaluationId].input
        ?.unavailableQuestions,
    ).toEqual([previous.result.follow_up_question]);
  }
});

it("rejects a public progress pointer or stage that disagrees with Session", async () => {
  const { sessionId } = await start();
  const session = await getQuestion(sessionId);
  expect(sessionSchema.safeParse(session).success).toBe(true);
  expect(
    sessionSchema.safeParse({
      ...session,
      activeCoaching: {
        ...session.activeCoaching,
        evaluationId: crypto.randomUUID(),
      },
    }).success,
  ).toBe(false);
  expect(
    sessionSchema.safeParse({
      ...session,
      activeAttempt: { ...session.activeAttempt, status: "completed" },
    }).success,
  ).toBe(false);
});

it.each(corpus.facts)(
  "provides structured output and input fixtures for $name (no real-model claim)",
  (fixture) => {
    const result = coachingResultSchema.parse({
      status: "completed",
      conclusion_score: 6,
      specificity_score: 6,
      reasoning_score: 6,
      good_point: "本人が述べた情報を使います。",
      improvement: "確実な情報を確認します。",
      follow_up_question: null,
      example: fixture.example,
    });
    for (const text of fixture.exclude)
      expect(result.example).not.toContain(text);
    expect(scoreValues(fixture.initial, 6, 6, 6).totalScore).toBe(18);
  },
);
