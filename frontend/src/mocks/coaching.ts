/** @file coaching.ts @description V2 Mock aggregate transitions and deterministic scenarios. */
import {
  isFeedbackV2,
  feedbackV2Schema,
  coachingResultSchema,
  type V2Answer,
  type FeedbackV2,
  type CoachingProgress,
} from "@/lib/api/schemas";
import { scoreValues } from "@/lib/textLimits";
import type { MockState, MockInput } from "./store";

export class MockConflict extends Error {
  constructor(
    public code = "SESSION_STATE_CONFLICT",
    public status = 409,
  ) {
    super(code);
  }
}
const signature = (text: string) => text.normalize("NFKC").replace(/\s/gu, "");
const unavailable = (text: string) =>
  [
    "分からない",
    "わからない",
    "特にない",
    "思いつかない",
    "覚えていない",
    "ありません",
    "特にありません",
    "わかりません",
    "分かりません",
    "思いつきません",
    "覚えていません",
  ].includes(signature(text).replace(/[。.!！]+$/u, ""));

function sync(state: MockState, progress: CoachingProgress) {
  const attempt = state.attempts[progress.attemptId];
  const session = state.sessions[attempt.feedback.sessionId];
  state.coachings[progress.attemptId] = progress;
  session.activeCoaching = structuredClone(progress);
}

export function acceptCoaching(
  state: MockState,
  sessionId: string,
  body: V2Answer,
) {
  const session = state.sessions[sessionId];
  const active = session.activeAttempt;
  const previous = active ? state.attempts[active.attemptId] : undefined;
  const head = active ? state.coachings[active.attemptId] : undefined;
  if ("questionId" in body && body.questionId !== session.question.id)
    throw new MockConflict();
  if (body.kind === "initial_answer") {
    if (
      previous &&
      (isFeedbackV2(previous.feedback) ||
        previous.evaluation.status !== "failed")
    )
      throw new MockConflict();
  } else {
    const target =
      body.kind === "retry_attempt" ? body.fromAttemptId : body.attemptId;
    if (!state.attempts[target] || !state.evaluations[body.fromEvaluationId])
      throw new MockConflict("ATTEMPT_NOT_FOUND", 404);
    if (
      !active ||
      target !== active.attemptId ||
      body.fromEvaluationId !== active.evaluationId
    )
      throw new MockConflict();
    if (body.kind === "retry_attempt") {
      if (active.status !== "completed" || (head && head.stage !== "completed"))
        throw new MockConflict();
    } else if (
      !head ||
      head.stage !==
        (body.kind === "coaching_answer" ? "awaiting_answer" : "failed")
    )
      throw new MockConflict();
  }
  const fresh = body.kind === "initial_answer" || body.kind === "retry_attempt";
  const attemptId = fresh ? crypto.randomUUID() : active!.attemptId;
  const evaluationId = crypto.randomUUID();
  let input: MockInput;
  let progress: CoachingProgress;
  if (fresh) {
    const answer = (
      body as Extract<V2Answer, { kind: "initial_answer" | "retry_attempt" }>
    ).answer;
    input = {
      initialAnswer: answer,
      history: [],
      count: 0,
      unavailableQuestions: [],
    };
    progress = {
      attemptId,
      evaluationId,
      stage: "evaluating",
      initialAnswer: answer,
      latestAnswer: answer,
      coachingHistory: [],
      coachingCount: 0,
      followUpQuestion: null,
      lastSuccessfulEvaluationId: null,
    };
  } else {
    input = structuredClone(state.evaluations[active!.evaluationId].input!);
    progress = structuredClone(head!);
    if (body.kind === "coaching_answer") {
      const question = head!.followUpQuestion!;
      input.history.push({ question, answer: body.answer });
      input.count++;
      if (unavailable(body.answer)) input.unavailableQuestions.push(question);
    }
    progress = {
      ...progress,
      evaluationId,
      stage: "evaluating",
      coachingHistory: structuredClone(input.history),
      coachingCount: input.count,
      latestAnswer: input.history.at(-1)?.answer ?? input.initialAnswer,
      followUpQuestion: null,
    };
  }
  const result = {
    status: "completed" as const,
    conclusion_score: 8,
    specificity_score: 8,
    reasoning_score: 8,
    good_point: "これは検証用のサンプル評価です。",
    improvement: "実際の採点品質は実Providerの評価試験で確認します。",
    follow_up_question: null,
    example: progress.latestAnswer,
  };
  const feedback: FeedbackV2 = {
    feedbackVersion: 2,
    attemptId,
    evaluationId,
    sessionId,
    question: structuredClone(session.question),
    questionNumber: session.questionNumber,
    answer: input.initialAnswer,
    latestAnswer: progress.latestAnswer,
    coachingHistory: structuredClone(input.history),
    coachingCount: input.count,
    result,
    ...scoreValues(input.initialAnswer, 8, 8, 8),
    createdAt: new Date().toISOString(),
  };
  const evaluation = {
    attemptId,
    evaluationId,
    status: "processing" as const,
    feedbackVersion: 2 as const,
  };
  const record = {
    feedback,
    evaluation,
    input,
    polls: 0,
    startedAt: Date.now(),
  };
  state.evaluations[evaluationId] = record;
  state.attempts[attemptId] = {
    ...structuredClone(record),
    initialEvaluationId: fresh ? evaluationId : previous!.initialEvaluationId,
  };
  session.activeAttempt = evaluation;
  sync(state, progress);
  return {
    status: 202,
    body: { attemptId, evaluationId, status: "processing" },
  };
}

export function pollCoaching(
  state: MockState,
  evaluationId: string,
  scenario: string,
) {
  const record = state.evaluations[evaluationId];
  if (!record || !isFeedbackV2(record.feedback)) return null;
  if (record.evaluation.status !== "processing") return record.evaluation;
  record.polls++;
  if (
    scenario === "never" ||
    record.polls < 3 ||
    (scenario === "slow" && Date.now() - record.startedAt <= 35000)
  )
    return record.evaluation;
  const input = record.input!;
  const old = record.feedback;
  const questions = [
    "そう考えるきっかけとなった経験はありますか？",
    "そのとき、あなた自身は何をしましたか？",
    "その経験が考えにつながった理由を教えてください。",
  ];
  const ask =
    input.count < 3 &&
    (scenario === "coaching_max" ||
      (scenario === "coaching" && input.count === 0) ||
      (scenario === "multiline_question" && input.count === 0) ||
      (scenario === "contradiction" && input.count === 0));
  let question =
    scenario === "multiline_question"
      ? "そのとき、あなた自身は\n何をしましたか？"
      : questions[input.count];
  if (scenario === "contradiction")
    question = "確認したい数について、どちらの説明が正しいでしょうか？";
  const raw = {
    ...old.result,
    status: ask ? "coaching" : "completed",
    specificity_score: ask
      ? 6
      : scenario === "low_score" || scenario === "coaching_max"
        ? 5
        : 8,
    follow_up_question: ask ? question : null,
    example: ask ? null : old.latestAnswer,
  };
  const parsed = coachingResultSchema.safeParse(raw);
  const duplicate =
    ask &&
    [
      ...input.history.map((h) => h.question),
      ...input.unavailableQuestions,
    ].some((q) => signature(q) === signature(question));
  const failed =
    ["evaluation_failed", "invalid_provider"].includes(scenario) ||
    !parsed.success ||
    duplicate;
  const progress = state.coachings[old.attemptId];
  if (failed) {
    record.evaluation = {
      evaluationId,
      attemptId: old.attemptId,
      status: "failed",
      feedbackVersion: 2,
      error: {
        code: "EVALUATION_FAILED",
        message: "Evaluation could not be completed.",
      },
    };
  } else {
    record.feedback = feedbackV2Schema.parse({
      ...old,
      result: parsed.data,
      ...scoreValues(
        old.answer,
        parsed.data.conclusion_score,
        parsed.data.specificity_score,
        parsed.data.reasoning_score,
      ),
    });
    record.evaluation = {
      evaluationId,
      attemptId: old.attemptId,
      status: "completed",
      feedbackVersion: 2,
    };
  }
  // A historical record must never update the current aggregate.
  if (progress.evaluationId === evaluationId) {
    progress.stage = failed ? "failed" : ask ? "awaiting_answer" : "completed";
    progress.followUpQuestion = failed || !ask ? null : question;
    if (!failed) progress.lastSuccessfulEvaluationId = evaluationId;
    state.attempts[old.attemptId] = {
      ...structuredClone(record),
      initialEvaluationId: state.attempts[old.attemptId].initialEvaluationId,
    };
    state.sessions[old.sessionId].activeAttempt = record.evaluation;
    sync(state, progress);
  }
  return record.evaluation;
}
