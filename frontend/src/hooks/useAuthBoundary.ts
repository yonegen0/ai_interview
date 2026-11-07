/** @file useAuthBoundary.ts @description State and side-effect controller for useAuthBoundary. */
"use client";
import { usePathname, useSearchParams } from "next/navigation";
import { auth } from "@/lib/auth/session";
import { useAuthSession } from "./useAuthSession";
export function useAuthBoundary(admin = false) {
  const state = useAuthSession();
  const pathname = usePathname();
  const params = useSearchParams();
  const status =
    state.phase === "restoring" ||
    (state.phase === "refreshing" && !state.sub)
      ? ("restoring" as const)
      : state.phase === "temporarily_unavailable"
        ? ("temporarily_unavailable" as const)
      : (state.phase !== "authenticated" && state.phase !== "refreshing") || !state.sub
        ? ("anonymous" as const)
        : admin && !state.groups.includes("ADMIN")
          ? ("forbidden" as const)
          : ("allowed" as const);
  const retainedScope = auth.retainedViewScope();
  return {
    // The hidden-view owner is never used for API authorization.
    ownerKey: `${retainedScope ?? auth.scope() ?? "anonymous"}:${auth.generation()}`,
    preserveMounted: !!retainedScope &&
      (status === "restoring" || status === "temporarily_unavailable"),
    status,
    error: state.error,
    onRetry: () => { void auth.recheck().catch(() => undefined); },
    loginUrl: `/login/?returnTo=${encodeURIComponent(pathname + (params.size ? `?${params}` : ""))}`,
  };
}
