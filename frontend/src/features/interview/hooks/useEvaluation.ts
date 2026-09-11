/** @file useEvaluation.ts @description 中断・再開・長時間待機を扱う評価Query */
"use client";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { getEvaluation } from "@/lib/api/interview";
export type EvaluationTiming = {
  longWaitSeconds: number;
  autoPauseSeconds: number;
  pollingIntervalMs: number;
};
export const defaultEvaluationTiming: EvaluationTiming = {
  longWaitSeconds: 30,
  autoPauseSeconds: 120,
  pollingIntervalMs: 2000,
};
const subscribe = (listener: () => void) => {
  document.addEventListener("visibilitychange", listener);
  window.addEventListener("online", listener);
  window.addEventListener("offline", listener);
  return () => {
    document.removeEventListener("visibilitychange", listener);
    window.removeEventListener("online", listener);
    window.removeEventListener("offline", listener);
  };
};
export const useEvaluation = (
  id: string | undefined,
  timing: EvaluationTiming = defaultEvaluationTiming,
) => {
  const active = useSyncExternalStore(
    subscribe,
    () => document.visibilityState === "visible" && navigator.onLine,
    () => true,
  );
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    setElapsed(0);
  }, [id]);
  const query = useQuery({
    queryKey: ["evaluation", id],
    queryFn: ({ signal }) => getEvaluation(id!, signal),
    enabled: (q) =>
      !!id &&
      active &&
      elapsed < timing.autoPauseSeconds &&
      (!q.state.data || q.state.data.status === "processing"),
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
    refetchIntervalInBackground: false,
    refetchInterval: (q) =>
      active &&
      elapsed < timing.autoPauseSeconds &&
      !q.state.error &&
      (!q.state.data || q.state.data.status === "processing")
        ? timing.pollingIntervalMs
        : false,
  });
  const terminal =
    query.data?.status === "completed" || query.data?.status === "failed";
  useEffect(() => {
    if (!id || terminal) return;
    const start = Date.now();
    const timer = setInterval(
      () => setElapsed(Math.floor((Date.now() - start) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [id, terminal]);
  return {
    ...query,
    elapsed,
    paused: !active || elapsed >= timing.autoPauseSeconds || !!query.error,
    terminal,
  };
};
