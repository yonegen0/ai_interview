/** @file practiceProgress.ts @description 本人の質問別完了数を取得する。 */
import { z } from "zod";
import { request } from "./client";

export const practiceProgressSchema = z.object({
  bankVersion: z.number().int().nonnegative(),
  totalQuestions: z.number().int().nonnegative(),
  completedQuestions: z.number().int().nonnegative(),
  nextIncompleteQuestionId: z.string().uuid().nullable(),
}).refine((value) =>
  value.completedQuestions <= value.totalQuestions &&
  ((value.totalQuestions > 0 && value.completedQuestions < value.totalQuestions) ===
    (value.nextIncompleteQuestionId !== null))
);

export type PracticeProgress = z.infer<typeof practiceProgressSchema>;

export const getPracticeProgress = (signal?: AbortSignal) =>
  request("/me/practice-progress", practiceProgressSchema, { signal });

export const practiceResumeSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("none") }).strict(),
  z.object({ status: z.literal("changed") }).strict(),
  z.object({
    status: z.literal("resume"),
    reason: z.enum(["processing", "draft", "local"]),
    sessionId: z.string().uuid(),
    questionNumber: z.number().int().positive().optional(),
  }).strict(),
]);

export type PracticeResume = z.infer<typeof practiceResumeSchema>;

export const getPracticeResume = (
  questionId: string, localSessionId?: string, localPending = false
) => {
  const query = new URLSearchParams({ questionId });
  if (localSessionId) query.set("localSessionId", localSessionId);
  if (localPending) query.set("localPending", "1");
  return request(`/me/practice-resume?${query.toString()}`, practiceResumeSchema);
};
