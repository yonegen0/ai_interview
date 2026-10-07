/** @file useAuthSession.ts @description State and side-effect controller for useAuthSession. */
"use client";
import { useEffect, useSyncExternalStore } from "react";
import { auth } from "@/lib/auth/session";
export function useAuthSession() {
  const state = useSyncExternalStore(
    auth.subscribe,
    auth.snapshot,
    auth.serverSnapshot,
  );
  useEffect(() => {
    void auth.initialize();
  }, []);
  return state;
}
