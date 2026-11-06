/** @file history.ts @description JWT本人限定の履歴一覧・集計API契約。 */
import { z } from "zod";
import { assistModeSchema } from "./star";

export const historyFilterSchema = z.enum([
  "all", "normal", "coaching", "assist", "star", "prep",
  "motivation", "career_change", "career_plan",
]);
export type HistoryMode = z.infer<typeof historyFilterSchema>;
export const historyPeriodSchema = z.enum(["all", "today", "7d", "30d"]);
export type HistoryPeriod = z.infer<typeof historyPeriodSchema>;
export const historyItemSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(["normal", "coaching", "assist"]),
  label: z.string().min(1),
  category: z.string().nullable(),
  createdAt: z.number().int().nonnegative(),
  status: z.enum([
    "processing", "completed", "failed", "QUEUED", "PREPARED", "STARTED",
    "SUCCEEDED", "NEEDS_INFORMATION", "CANCELLED", "FAILED_BEFORE_START",
    "FAILED_AFTER_START", "OUTCOME_UNKNOWN",
  ]),
  score: z.number().int().nonnegative().nullable(),
  scoreMax: z.union([z.literal(100), z.literal(30)]).nullable(),
  attemptId: z.uuid().nullable(),
  evaluationId: z.uuid().nullable(),
  generationId: z.uuid().nullable(),
  assistType: assistModeSchema.nullable(),
}).strict().superRefine((value, ctx) => {
  const attempt = value.kind !== "assist";
  if ((attempt && (!value.attemptId || !value.evaluationId ||
    value.generationId || value.assistType || value.scoreMax !== (value.kind === "coaching" ? 30 : 100))) ||
    (!attempt && (!value.generationId || value.attemptId || value.evaluationId ||
    !value.assistType || value.scoreMax !== null || value.score !== null)) ||
    (value.score !== null && (value.status !== "completed" || !attempt || value.score > (value.scoreMax ?? 0)))) {
    ctx.addIssue({ code: "custom", message: "履歴の評価種別が一致しません。" });
  }
});
export type HistoryItem = z.infer<typeof historyItemSchema>;
export const usageSchema = z.object({
  practiceAttempts: z.number().int().nonnegative(),
  evaluatedAttempts: z.number().int().nonnegative(),
  assistGenerations: z.number().int().nonnegative(),
  normalAverage: z.number().min(0).max(100).nullable(),
  coachingAverage: z.number().min(0).max(30).nullable(),
}).strict();
export const historyResponseSchema = z.object({
  items: z.array(historyItemSchema).max(100),
  nextCursor: z.string().min(1).nullable(),
  usage: usageSchema.nullable(),
}).strict();
export type HistoryResponse = z.infer<typeof historyResponseSchema>;
