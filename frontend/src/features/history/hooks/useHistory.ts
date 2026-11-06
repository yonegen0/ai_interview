/** @file useHistory.ts @description 所有者別・フィルター別の履歴をページ単位で管理する。 */
"use client";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { getHistory } from "@/lib/api/history";
import { getQuota } from "@/lib/api/star";
import { type HistoryMode, type HistoryPeriod } from "@/lib/api/schemas/history";

export function useHistory(owner: string, open: boolean, mode: HistoryMode, period: HistoryPeriod) {
  const enabled = Boolean(owner && open);
  const records = useInfiniteQuery({
    queryKey: [owner, "history", mode, period],
    queryFn: ({ pageParam, signal }) => getHistory({ mode, period, limit: 5, cursor: pageParam, signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled,
  });
  const usage = useQuery({
    queryKey: [owner, "history", "usage"],
    queryFn: ({ signal }) => getHistory({ mode: "all", period: "all", limit: 5, signal }),
    enabled,
  });
  const quota = useQuery({
    queryKey: [owner, "star-assist", "quota"],
    queryFn: ({ signal }) => getQuota(signal),
    enabled,
  });
  return { records, usage, quota };
}
