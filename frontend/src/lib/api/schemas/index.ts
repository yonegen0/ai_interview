/** @file index.ts @description Frontend v2 API契約の唯一の定義元 */
import { z } from "zod";
import { countCodePoints, scoreValues } from "@/lib/textLimits";

export const categories = {
  self_introduction: "自己紹介",
  company_selection: "企業選び",
  experience: "仕事経験",
  job_change: "転職理由",
  motivation: "志望動機",
  career: "キャリア",
  strengths: "強み",
  weaknesses: "弱み",
  conditions: "希望条件",
  questions: "逆質問",
  difficulty: "困難・失敗",
} as const;
export const activeCategoryIds = [
  "self_introduction",
  "company_selection",
  "experience",
  "job_change",
  "motivation",
  "career",
  "strengths",
  "weaknesses",
  "conditions",
  "questions",
] as const;
export const activeCategorySchema = z.enum(activeCategoryIds);
export const categorySchema = z.enum(
  Object.keys(categories) as [
    keyof typeof categories,
    ...Array<keyof typeof categories>,
  ],
);
export const idSchema = z.uuid();
export const ANSWER_MAX_LENGTH = 500;
export const answerSchema = z
  .string()
  .min(1, "回答を入力してください。")
  .refine(
    (value) => value.length <= ANSWER_MAX_LENGTH,
    `${ANSWER_MAX_LENGTH}文字以内で入力してください。`,
  )
  .refine(
    (value) => value.trim().length > 0,
    "空白以外の回答を入力してください。",
  );
const limitedText = (maximum: number) =>
  z
    .string()
    .min(1)
    .refine((v) => v.trim().length > 0, "空白以外の内容を入力してください。")
    .refine(
      (v) => countCodePoints(v) <= maximum,
      `${maximum}文字以内で入力してください。`,
    );
export const coachingAnswerSchema = limitedText(400);
export const coachingQuestionSchema = limitedText(200);
export const formSchema = z.object({ answer: coachingAnswerSchema });
export const coachingHistoryItemSchema = z
  .object({ question: coachingQuestionSchema, answer: coachingAnswerSchema })
  .strict();
export const activeCoachingSchema = z
  .object({
    attemptId: idSchema,
    evaluationId: idSchema,
    stage: z.enum(["evaluating", "awaiting_answer", "completed", "failed"]),
    initialAnswer: coachingAnswerSchema,
    latestAnswer: coachingAnswerSchema,
    coachingHistory: z.array(coachingHistoryItemSchema).max(3),
    coachingCount: z.number().int().min(0).max(3),
    followUpQuestion: coachingQuestionSchema.nullable(),
    lastSuccessfulEvaluationId: idSchema.nullable(),
  })
  .strict()
  .superRefine((v, ctx) => {
    if (
      v.coachingCount !== v.coachingHistory.length ||
      v.latestAnswer !==
        (v.coachingHistory.at(-1)?.answer ?? v.initialAnswer) ||
      (v.stage === "awaiting_answer") !== (v.followUpQuestion !== null) ||
      (v.coachingCount === 3 && v.stage === "awaiting_answer") ||
      (["awaiting_answer", "completed"].includes(v.stage) &&
        v.lastSuccessfulEvaluationId !== v.evaluationId)
    )
      ctx.addIssue({
        code: "custom",
        message: "コーチングの進捗情報が一致しません。",
      });
  });
export const createSchema = z.union([
  z
    .object({ mode: z.literal("full"), difficulty: z.literal("standard") })
    .strict(),
  z
    .object({
      mode: z.literal("category"),
      category: activeCategorySchema,
      difficulty: z.literal("standard"),
    })
    .strict(),
  z.object({
    category: categorySchema,
    difficulty: z.literal("standard"),
    mode: z.never().optional(),
  }),
]);
export const createdSchema = z.object({ sessionId: idSchema });
export const questionSchema = z.object({
  id: idSchema,
  category: categorySchema,
  difficulty: z.literal("standard"),
  question: z.string().min(1),
});
export const errorSchema = z.object({ code: z.string(), message: z.string() });
export const statusSchema = z.enum(["processing", "completed", "failed"]);
export const attemptSchema = z.object({
  attemptId: idSchema,
  evaluationId: idSchema,
  status: statusSchema,
});
export const sessionSchema = z
  .object({
    sessionId: idSchema,
    question: questionSchema,
    questionNumber: z.number().int().positive(),
    activeAttempt: attemptSchema.nullable(),
    activeCoaching: activeCoachingSchema.optional(),
    mode: z.enum(["full", "category", "legacy"]).optional(),
    totalQuestions: z.number().int().positive().optional(),
    hasNext: z.boolean().optional(),
  })
  .superRefine((value, ctx) => {
    const coaching = value.activeCoaching;
    if (
      coaching &&
      (!value.activeAttempt ||
        coaching.attemptId !== value.activeAttempt.attemptId ||
        coaching.evaluationId !== value.activeAttempt.evaluationId ||
        value.activeAttempt.status !==
          (coaching.stage === "evaluating"
            ? "processing"
            : coaching.stage === "failed"
              ? "failed"
              : "completed"))
    )
      ctx.addIssue({
        code: "custom",
        message: "練習の進行と評価が一致しません。",
      });
    if (
      value.mode !== undefined ||
      value.totalQuestions !== undefined ||
      value.hasNext !== undefined
    ) {
      if (
        value.mode === undefined ||
        value.totalQuestions === undefined ||
        value.hasNext === undefined ||
        value.hasNext !==
          (value.mode === "legacy" ||
            value.questionNumber < value.totalQuestions) ||
        (value.mode !== "legacy" && value.questionNumber > value.totalQuestions)
      )
        ctx.addIssue({
          code: "custom",
          message: "練習の進捗情報を確認できません。",
        });
    }
  });
export const managedQuestionSchema = questionSchema
  .extend({
    category: activeCategorySchema,
    question: z
      .string()
      .min(1, "質問本文は1〜200文字で入力してください。")
      .max(1000, "質問本文を確認してください。")
      .refine((value) => value.trim().length > 0, "質問を入力してください。"),
  })
  .strict();
export const bankSaveSchema = z
  .object({
    expectedVersion: z
      .number()
      .int()
      .nonnegative()
      .max(Number.MAX_SAFE_INTEGER),
    questions: z.array(managedQuestionSchema).min(1).max(100),
  })
  .strict()
  .refine(
    (value) =>
      new Set(value.questions.map((q) => q.id.toLowerCase())).size ===
      value.questions.length,
    "質問IDが重複しています。",
  );
export function bankSaveSchemaForBaseline(
  baseline: ReadonlyArray<z.infer<typeof managedQuestionSchema>>,
) {
  const previous = new Map(baseline.map((q) => [q.id, q.question]));
  return bankSaveSchema.superRefine((value, ctx) => {
    value.questions.forEach((q, i) => {
      if (
        previous.get(q.id) !== q.question &&
        countCodePoints(q.question) > 200
      )
        ctx.addIssue({
          code: "custom",
          path: ["questions", i, "question"],
          message: "質問本文は200文字以内にしてください。",
        });
    });
  });
}
export const bankSchema = z.object({
  version: z.number().int().nonnegative(),
  updatedAt: z.iso.datetime().nullable(),
  questions: z.array(managedQuestionSchema).min(1).max(100),
});
export const bankReceiptSchema = bankSchema
  .omit({ questions: true })
  .extend({ totalQuestions: z.number().int().positive().max(100) });
export const practiceOptionsSchema = z.object({
  bankVersion: z.number().int().nonnegative(),
  totalQuestions: z.number().int().positive().max(100),
  categories: z.array(
    z.object({
      id: activeCategorySchema,
      label: z.string(),
      questionCount: z.number().int().positive(),
    }),
  ),
});
export type CreateInput = z.infer<typeof createSchema>;
export type QuestionBank = z.infer<typeof bankSchema>;
export type BankSave = z.infer<typeof bankSaveSchema>;
export type ManagedQuestion = z.infer<typeof managedQuestionSchema>;
export const legacySubmitSchema = z.object({
  kind: z.never().optional(),
  questionId: idSchema,
  answer: answerSchema,
});
export const v2SubmitSchema = z.discriminatedUnion("kind", [
  z
    .object({
      kind: z.literal("initial_answer"),
      questionId: idSchema,
      answer: coachingAnswerSchema,
    })
    .strict(),
  z
    .object({
      kind: z.literal("coaching_answer"),
      questionId: idSchema,
      answer: coachingAnswerSchema,
      attemptId: idSchema,
      fromEvaluationId: idSchema,
    })
    .strict(),
  z
    .object({
      kind: z.literal("retry_evaluation"),
      attemptId: idSchema,
      fromEvaluationId: idSchema,
    })
    .strict(),
  z
    .object({
      kind: z.literal("retry_attempt"),
      questionId: idSchema,
      answer: coachingAnswerSchema,
      fromAttemptId: idSchema,
      fromEvaluationId: idSchema,
    })
    .strict(),
]);
export const submitSchema = z
  .unknown()
  .transform(
    (
      value,
      ctx,
    ): z.infer<typeof legacySubmitSchema> | z.infer<typeof v2SubmitSchema> => {
      const parsed = (
        typeof value === "object" &&
        value !== null &&
        Object.hasOwn(value, "kind")
          ? v2SubmitSchema
          : legacySubmitSchema
      ).safeParse(value);
      if (!parsed.success) {
        parsed.error.issues.forEach((issue) =>
          ctx.addIssue({
            code: "custom",
            message: issue.message,
            path: issue.path,
          }),
        );
        return z.NEVER;
      }
      return parsed.data;
    },
  );
export const nextSchema = z.object({ fromAttemptId: idSchema });
export const evaluationSchema = z.discriminatedUnion("status", [
  z.object({
    evaluationId: idSchema,
    attemptId: idSchema,
    status: z.literal("processing"),
    feedbackVersion: z.literal(2).optional(),
  }),
  z.object({
    evaluationId: idSchema,
    attemptId: idSchema,
    status: z.literal("completed"),
    feedbackVersion: z.literal(2).optional(),
  }),
  z.object({
    evaluationId: idSchema,
    attemptId: idSchema,
    status: z.literal("failed"),
    error: errorSchema,
    feedbackVersion: z.literal(2).optional(),
  }),
]);
export const legacyFeedbackSchema = z.object({
  attemptId: idSchema,
  sessionId: idSchema,
  question: questionSchema,
  questionNumber: z.number().int().positive(),
  answer: answerSchema,
  score: z.number().int().min(0).max(100),
  summary: z.string(),
  strengths: z.array(z.string()),
  improvements: z.array(z.string()),
  exampleAnswer: z.string().optional(),
  createdAt: z.iso.datetime(),
});
export const coachingResultSchema = z
  .object({
    status: z.enum(["coaching", "completed"]),
    conclusion_score: z.number().int().min(0).max(10),
    specificity_score: z.number().int().min(0).max(10),
    reasoning_score: z.number().int().min(0).max(10),
    good_point: coachingQuestionSchema,
    improvement: coachingQuestionSchema,
    follow_up_question: coachingQuestionSchema.nullable(),
    example: coachingAnswerSchema.nullable(),
  })
  .strict()
  .superRefine((v, ctx) => {
    if (
      v.status === "coaching"
        ? v.follow_up_question === null || v.example !== null
        : v.follow_up_question !== null || v.example === null
    )
      ctx.addIssue({
        code: "custom",
        message: "評価結果の状態が一致しません。",
      });
  });
export const feedbackV2Schema = z
  .object({
    feedbackVersion: z.literal(2),
    attemptId: idSchema,
    evaluationId: idSchema,
    sessionId: idSchema,
    question: questionSchema,
    questionNumber: z.number().int().positive(),
    answer: coachingAnswerSchema,
    latestAnswer: coachingAnswerSchema,
    coachingHistory: z.array(coachingHistoryItemSchema).max(3),
    coachingCount: z.number().int().min(0).max(3),
    result: coachingResultSchema,
    answerLength: z.number().int(),
    lengthPenalty: z.number().int(),
    baseScore: z.number().int(),
    totalScore: z.number().int(),
    rank: z.enum(["S", "A", "B", "C"]),
    createdAt: z.iso.datetime(),
  })
  .strict()
  .superRefine((v, ctx) => {
    const scores = scoreValues(
      v.answer,
      v.result.conclusion_score,
      v.result.specificity_score,
      v.result.reasoning_score,
    );
    if (
      Object.entries(scores).some(
        ([k, value]) => v[k as keyof typeof scores] !== value,
      ) ||
      v.coachingCount !== v.coachingHistory.length ||
      v.latestAnswer !== (v.coachingHistory.at(-1)?.answer ?? v.answer) ||
      (v.coachingCount === 3 && v.result.status === "coaching")
    )
      ctx.addIssue({
        code: "custom",
        message: "評価結果の集計が一致しません。",
      });
  });
export const feedbackSchema = z
  .unknown()
  .transform(
    (
      value,
      ctx,
    ):
      | z.infer<typeof legacyFeedbackSchema>
      | z.infer<typeof feedbackV2Schema> => {
      const hasVersion =
        typeof value === "object" &&
        value !== null &&
        Object.hasOwn(value, "feedbackVersion");
      const parsed = (
        hasVersion ? feedbackV2Schema : legacyFeedbackSchema
      ).safeParse(value);
      if (!parsed.success) {
        parsed.error.issues.forEach((issue) =>
          ctx.addIssue({
            code: "custom",
            message: issue.message,
            path: issue.path,
          }),
        );
        return z.NEVER;
      }
      return parsed.data;
    },
  );
export type FeedbackV2 = z.infer<typeof feedbackV2Schema>;
export type LegacyFeedback = z.infer<typeof legacyFeedbackSchema>;
export const isFeedbackV2 = (value: Feedback): value is FeedbackV2 =>
  "feedbackVersion" in value;
export type CoachingProgress = z.infer<typeof activeCoachingSchema>;
export type V2Answer = z.infer<typeof v2SubmitSchema>;
export type Category = z.infer<typeof categorySchema>;
export type Question = z.infer<typeof questionSchema>;
export type Session = z.infer<typeof sessionSchema>;
export type Attempt = z.infer<typeof attemptSchema>;
export type Evaluation = z.infer<typeof evaluationSchema>;
export type Feedback = z.infer<typeof feedbackSchema>;
export type Answer = z.infer<typeof submitSchema>;
