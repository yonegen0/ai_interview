/** @file index.ts @description Storybookで共有する決定的な面接データFixture。 */
import {
  evaluationSchema,
  feedbackSchema,
  questionSchema,
  sessionSchema,
  type Evaluation,
  type Feedback,
  type Question,
  type Session,
} from "@/lib/api/schemas";
import type { MockState } from "@/mocks/store";
import { questions } from "@/mocks/data/questions";

export const storyIds = {
  session: "10000000-0000-4000-8000-000000000001",
  otherSession: "10000000-0000-4000-8000-000000000002",
  currentAttempt: "20000000-0000-4000-8000-000000000001",
  previousAttempt: "20000000-0000-4000-8000-000000000002",
  evaluation: "30000000-0000-4000-8000-000000000001",
  idempotency: "40000000-0000-4000-8000-000000000001",
  question: questions[0].id,
} as const;

export const storyNow = "2026-09-09T00:00:00.000Z";
export const storyNowMs = Date.parse(storyNow);

export const exactText = (length: number): string => {
  const source = "私は課題を整理し、周囲と相談しながら行動して成果につなげました。";
  const value = source.repeat(Math.ceil(length / source.length)).slice(0, length);
  if (value.length !== length) throw new Error(`Fixture length mismatch: ${length}`);
  return value;
};

export const storyTexts = {
  text100: exactText(100),
  text500: exactText(500),
  text501: exactText(501),
  text1000: exactText(1000),
} as const;

export const createQuestionFixture = (
  overrides: Partial<Question> = {},
): Question => questionSchema.parse({ ...questions[0], ...overrides });

export const createSessionFixture = (
  overrides: Partial<Session> = {},
): Session =>
  sessionSchema.parse({
    sessionId: storyIds.session,
    question: createQuestionFixture(),
    questionNumber: 1,
    activeAttempt: null,
    ...overrides,
  });

export const createEvaluationFixture = (
  status: Evaluation["status"] = "completed",
): Evaluation =>
  evaluationSchema.parse(
    status === "failed"
      ? {
          attemptId: storyIds.currentAttempt,
          evaluationId: storyIds.evaluation,
          status,
          error: { code: "EVALUATION_FAILED", message: "評価に失敗しました。" },
        }
      : {
          attemptId: storyIds.currentAttempt,
          evaluationId: storyIds.evaluation,
          status,
        },
  );

export const createFeedbackFixture = (
  overrides: Partial<Feedback> = {},
): Feedback =>
  feedbackSchema.parse({
    attemptId: storyIds.currentAttempt,
    sessionId: storyIds.session,
    question: createQuestionFixture(),
    questionNumber: 1,
    answer: "経験を活かして貢献したいです。",
    score: 78,
    summary: "結論と具体例がつながっており、話の軸が伝わります。",
    strengths: ["結論が明確です。"],
    improvements: ["成果を数値で補足しましょう。"],
    exampleAnswer: "経験、行動、結果の順に説明してみましょう。",
    createdAt: storyNow,
    ...overrides,
  });

export const createStoryState = (options?: {
  session?: Session;
  feedback?: Feedback;
  evaluation?: Evaluation;
  polls?: number;
}): MockState => {
  const session = options?.session ?? createSessionFixture();
  const feedback = options?.feedback;
  const evaluation = options?.evaluation;
  return {
    version: 1,
    sessions: { [session.sessionId]: session },
    attempts:
      feedback && evaluation
        ? {
            [feedback.attemptId]: {
              feedback,
              evaluation,
              polls: options?.polls ?? 0,
              startedAt: storyNowMs,
            },
          }
        : {},
    requests: {},
    consumed: [],
  };
};

export const createCompletedState = (): MockState => {
  const evaluation = createEvaluationFixture("completed");
  const feedback = createFeedbackFixture();
  const session = createSessionFixture({
    activeAttempt: {
      attemptId: evaluation.attemptId,
      evaluationId: evaluation.evaluationId,
      status: evaluation.status,
    },
  });
  return createStoryState({ session, feedback, evaluation });
};

export const sessionRoute = `/practice/session/?sessionId=${storyIds.session}`;
export const resultRoute = `/result/?attemptId=${storyIds.currentAttempt}`;
