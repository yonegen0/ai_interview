/** @file useAdminUserHistory.ts @description Owner-bound, read-only ADMIN history queries. */
"use client";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { getAdminUserHistory } from "@/lib/api/adminUsers";
import type { HistoryMode, HistoryPeriod } from "@/lib/api/schemas/history";

export function useAdminUserHistory(
  adminSub: string, targetSub: string, mode: HistoryMode, period: HistoryPeriod,
) {
  const enabled = Boolean(adminSub && targetSub);
  const records = useInfiniteQuery({
    queryKey: [adminSub, "admin-user-history", targetSub, mode, period],
    queryFn: ({ pageParam, signal }) =>
      getAdminUserHistory(targetSub, { mode, period, cursor: pageParam, signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled,
  });
  const usage = useQuery({
    queryKey: [adminSub, "admin-user-usage", targetSub],
    queryFn: ({ signal }) => getAdminUserHistory(targetSub, { mode: "all", period: "all", signal }),
    enabled,
  });
  return { records, usage };
}
