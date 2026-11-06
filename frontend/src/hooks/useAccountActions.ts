/** @file useAccountActions.ts @description State and side-effect controller for useAccountActions. */
"use client";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { auth } from "@/lib/auth/session";
import { useAuthSession } from "./useAuthSession";
export function useAccountActions() {
  const state = useAuthSession();
  const client = useQueryClient();
  useEffect(() => {
    let previous = auth.generation();
    // Clear synchronously at the identity event, before new protected queries mount.
    // A token refresh keeps its generation and therefore keeps current queries.
    return auth.subscribe(() => {
      const current = auth.generation();
      if (previous !== current) {
        previous = current;
        void client.cancelQueries();
        client.clear();
      }
    });
  }, [client]);
  const authenticated = state.phase === "authenticated" ||
    (state.phase === "refreshing" && !!state.sub);
  return {
    authenticated,
    admin: authenticated && state.groups.includes("ADMIN"),
    sub: authenticated ? state.sub : null,
    phase: state.phase,
    onRetry: () => { void auth.recheck().catch(() => undefined); },
    onLogout: () => {
      void auth.logout();
    },
  };
}
