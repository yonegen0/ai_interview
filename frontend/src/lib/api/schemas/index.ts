/** @file index.ts @description Frontend v2 API契約の唯一の定義元 */
import { z } from "zod";

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
export const formSchema = z.object({ answer: answerSchema });
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
    mode: z.enum(["full", "category", "legacy"]).optional(),
    totalQuestions: z.number().int().positive().optional(),
    hasNext: z.boolean().optional(),
  })
  .superRefine((value, ctx) => {
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
      .min(1)
      .max(1000)
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
export const submitSchema = z.object({
  questionId: idSchema,
  answer: answerSchema,
});
export const nextSchema = z.object({ fromAttemptId: idSchema });
export const evaluationSchema = z.discriminatedUnion("status", [
  z.object({
    evaluationId: idSchema,
    attemptId: idSchema,
    status: z.literal("processing"),
  }),
  z.object({
    evaluationId: idSchema,
    attemptId: idSchema,
    status: z.literal("completed"),
  }),
  z.object({
    evaluationId: idSchema,
    attemptId: idSchema,
    status: z.literal("failed"),
    error: errorSchema,
  }),
]);
export const feedbackSchema = z.object({
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
export type Category = z.infer<typeof categorySchema>;
export type Question = z.infer<typeof questionSchema>;
export type Session = z.infer<typeof sessionSchema>;
export type Attempt = z.infer<typeof attemptSchema>;
export type Evaluation = z.infer<typeof evaluationSchema>;
export type Feedback = z.infer<typeof feedbackSchema>;
export type Answer = z.infer<typeof submitSchema>;
