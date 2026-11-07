/** @file useHomeProgress.ts @description 認証スコープ別のホーム進捗取得。 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuthSession } from "@/hooks/useAuthSession";
import { auth } from "@/lib/auth/session";
import { getPracticeProgress } from "@/lib/api/practiceProgress";

export function useHomeProgress() {
  const state = useAuthSession();
  const authenticated =
    (state.phase === "authenticated" || state.phase === "refreshing") && !!state.sub;
  const owner = authenticated ? auth.scope() : null;
  const generation = auth.generation();
  const query = useQuery({
    queryKey: [owner, generation, "practice-progress"],
    queryFn: ({ signal }) => getPracticeProgress(signal),
    enabled: authenticated && !!owner,
    staleTime: 30_000,
    // Revalidate when returning from a completed evaluation, even inside staleTime.
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  return {
    ...query,
    state,
    authenticated,
    data: authenticated ? query.data : undefined,
  };
}
