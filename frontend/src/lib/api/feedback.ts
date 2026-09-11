/** @file feedback.ts @description 結果APIアクセス */
import { request } from "./client";
import { feedbackSchema, idSchema } from "./schemas";
export const getFeedback = (id: string, signal?: AbortSignal) =>
  request(`/attempts/${idSchema.parse(id)}/feedback`, feedbackSchema, {
    signal,
  });
