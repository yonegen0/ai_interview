/** @file adminUsers.ts @description Typed ADMIN endpoints distinct from self-service APIs. */
import { request } from "./client";
import { feedbackSchema, feedbackWithReviewsSchema, idSchema } from "./schemas";
import { historyResponseSchema, type HistoryMode, type HistoryPeriod } from "./schemas/history";
import { adminUserListSchema, nicknameReceiptSchema } from "./schemas/adminUsers";

const userPath = (userId: string) => `/admin/users/${idSchema.parse(userId)}`;
export const getAdminUsers = (cursor?: string | null, signal?: AbortSignal) => {
  const params = new URLSearchParams({ limit: "60" });
  if (cursor) params.set("cursor", cursor);
  return request(`/admin/users?${params.toString()}`, adminUserListSchema, { signal });
};
export const getAdminUserHistory = (userId: string, options: {
  mode: HistoryMode; period: HistoryPeriod; cursor?: string | null; signal?: AbortSignal;
}) => {
  const params = new URLSearchParams({ mode: options.mode, period: options.period, limit: "5" });
  if (options.cursor) params.set("cursor", options.cursor);
  return request(`${userPath(userId)}/history?${params.toString()}`, historyResponseSchema, { signal: options.signal });
};
export const getAdminUserFeedback = async (
  userId: string, attemptId: string, evaluationId?: string | null, signal?: AbortSignal,
) => {
  const params = new URLSearchParams({ includeFollowUpReviews: "1" });
  if (evaluationId) params.set("evaluationId", idSchema.parse(evaluationId));
  const reply = await request(
    `${userPath(userId)}/attempts/${idSchema.parse(attemptId)}/feedback?${params}`,
    feedbackWithReviewsSchema.or(feedbackSchema), { signal },
  );
  return "feedback" in reply ? reply : { feedback: reply, followUpReviews: [] };
};
export const putAdminNickname = (userId: string, nickname: string) =>
  request(`${userPath(userId)}/nickname`, nicknameReceiptSchema, {
    method: "PUT", body: { nickname },
  });
