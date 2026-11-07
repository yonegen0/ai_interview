/** @file feedback.ts @description 結果APIアクセス */
import { request } from "./client";
import { feedbackSchema, feedbackWithReviewsSchema, idSchema } from "./schemas";
export const getFeedback = (
  id: string,
  signal?: AbortSignal,
  evaluationId?: string,
) =>
  request(
    `/attempts/${idSchema.parse(id)}/feedback${evaluationId !== undefined ? `?evaluationId=${idSchema.parse(evaluationId)}` : ""}`,
    feedbackSchema,
    {
      signal,
    },
  );

/** Opt-in review history; old backend responses remain readable without review data. */
export const getFeedbackWithReviews = async (
  id: string,
  signal?: AbortSignal,
  evaluationId?: string,
) => {
  const params = new URLSearchParams({ includeFollowUpReviews: "1" });
  if (evaluationId !== undefined) params.set("evaluationId", idSchema.parse(evaluationId));
  const raw = await request(
    `/attempts/${idSchema.parse(id)}/feedback?${params.toString()}`,
    feedbackWithReviewsSchema.or(feedbackSchema),
    { signal },
  );
  if ("feedback" in raw) return raw;
  return { feedback: raw, followUpReviews: [] };
};
