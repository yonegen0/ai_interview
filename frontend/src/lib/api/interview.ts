/** @file interview.ts @description 練習APIへの型付きアクセス */
import { request, ApiError } from "./client";
import {
  createSchema,
  createdSchema,
  idSchema,
  sessionSchema,
  submitSchema,
  attemptSchema,
  evaluationSchema,
  nextSchema,
  type Category,
  type Answer,
} from "./schemas";
const checkedId = (id: string) => {
  if (!idSchema.safeParse(id).success)
    throw new ApiError("VALIDATION_ERROR", 400);
  return id;
};
export const createSession = (category: Category, key: string) =>
  request("/sessions", createdSchema, {
    method: "POST",
    key,
    body: createSchema.parse({ category, difficulty: "standard" }),
  });
export const getQuestion = (id: string, signal?: AbortSignal) =>
  request(`/sessions/${checkedId(id)}/question`, sessionSchema, { signal });
export const submitAnswer = (id: string, body: Answer, key: string) =>
  request(`/sessions/${checkedId(id)}/answers`, attemptSchema, {
    method: "POST",
    key,
    body: submitSchema.parse(body),
  });
export const getEvaluation = (id: string, signal?: AbortSignal) =>
  request(`/evaluations/${checkedId(id)}`, evaluationSchema, { signal });
export const nextQuestion = (id: string, fromAttemptId: string, key: string) =>
  request(`/sessions/${checkedId(id)}/questions/next`, sessionSchema, {
    method: "POST",
    key,
    body: nextSchema.parse({ fromAttemptId }),
  });
