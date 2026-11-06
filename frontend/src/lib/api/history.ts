/** @file history.ts @description JWT本人の履歴一覧をZod検証付きで取得する。 */
import { request } from "./client";
import { historyResponseSchema, type HistoryMode, type HistoryPeriod } from "./schemas/history";

export const getHistory = ({
  mode = "all", period = "all", cursor, limit = 5, signal,
}: {
  mode?: HistoryMode;
  period?: HistoryPeriod;
  cursor?: string | null;
  limit?: number;
  signal?: AbortSignal;
}) => {
  const search = new URLSearchParams({ mode, period, limit: String(limit) });
  if (cursor) search.set("cursor", cursor);
  return request(`/me/history?${search.toString()}`, historyResponseSchema, { signal });
};
