/** @file index.ts @description Frontend v2 API契約の唯一の定義元 */
import { z } from "zod";

export const categories = {
  job_change: "転職理由",
  motivation: "志望動機",
  strengths: "自己PR・強み",
  experience: "仕事経験",
  difficulty: "困難・失敗",
  career: "キャリアプラン",
  questions: "逆質問",
} as const;
export const categorySchema = z.enum(
  Object.keys(categories) as [
    keyof typeof categories,
    ...Array<keyof typeof categories>,
  ],
);
export const idSchema = z.uuid();
export const answerSchema = z
  .string()
  .min(1, "回答を入力してください。")
  .max(2000, "2000文字以内で入力してください。")
  .refine(
    (value) => value.trim().length > 0,
    "空白以外の回答を入力してください。",
  );
export const formSchema = z.object({ answer: answerSchema });
export const createSchema = z.object({
  category: categorySchema,
  difficulty: z.literal("standard"),
});
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
export const sessionSchema = z.object({
  sessionId: idSchema,
  question: questionSchema,
  questionNumber: z.number().int().positive(),
  activeAttempt: attemptSchema.nullable(),
});
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
