/** @file useAuthBoundary.ts @description State and side-effect controller for useAuthBoundary. */
"use client";
import { usePathname, useSearchParams } from "next/navigation";
import { auth } from "@/lib/auth/session";
import { useAuthSession } from "./useAuthSession";
export function useAuthBoundary(admin = false) {
  const state = useAuthSession();
  const pathname = usePathname();
  const params = useSearchParams();
  return {
    ownerKey: `${auth.scope() ?? "anonymous"}:${auth.generation()}`,
    status:
      state.phase === "restoring"
        ? ("restoring" as const)
        : !state.sub
          ? ("anonymous" as const)
          : admin && !state.groups.includes("ADMIN")
            ? ("forbidden" as const)
            : ("allowed" as const),
    error: state.error,
    loginUrl: `/login/?returnTo=${encodeURIComponent(pathname + (params.size ? `?${params}` : ""))}`,
  };
}
