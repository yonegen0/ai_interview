/** @file practiceProgress.ts @description 本人の質問別完了数を取得する。 */
import { z } from "zod";
import { request } from "./client";

export const practiceProgressSchema = z.object({
  bankVersion: z.number().int().nonnegative(),
  totalQuestions: z.number().int().nonnegative(),
  completedQuestions: z.number().int().nonnegative(),
}).refine((value) => value.completedQuestions <= value.totalQuestions);

export type PracticeProgress = z.infer<typeof practiceProgressSchema>;

export const getPracticeProgress = (signal?: AbortSignal) =>
  request("/me/practice-progress", practiceProgressSchema, { signal });
