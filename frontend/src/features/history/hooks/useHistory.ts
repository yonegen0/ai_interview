/** @file useHistory.ts @description 所有者別・フィルター別の履歴をページ単位で管理する。 */
"use client";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { getHistory } from "@/lib/api/history";
import { getQuota } from "@/lib/api/star";
import { type HistoryMode, type HistoryPeriod } from "@/lib/api/schemas/history";

export function useHistory(owner: string, open: boolean, mode: HistoryMode, period: HistoryPeriod, tab: number) {
  const enabled = Boolean(owner && open);
  const allHistory = mode === "all" && period === "all";
  const records = useInfiniteQuery({
    queryKey: [owner, "history", mode, period],
    queryFn: ({ pageParam, signal }) => getHistory({ mode, period, limit: 5, cursor: pageParam, signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: enabled && (tab === 0 || allHistory),
  });
  const usage = useQuery({
    queryKey: [owner, "history", "usage"],
    queryFn: ({ signal }) => getHistory({ mode: "all", period: "all", limit: 5, signal }),
    // The all/all infinite query already contains a complete aggregate in page one.
    enabled: enabled && tab === 1 && !allHistory,
  });
  const quota = useQuery({
    queryKey: [owner, "star-assist", "quota"],
    queryFn: ({ signal }) => getQuota(signal),
    enabled: enabled && tab === 1,
  });
  return { records, usage, quota };
}
