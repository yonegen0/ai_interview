/** @file useFeedbackResult.ts @description State and side-effect controller for useFeedbackResult. */
"use client";
import { useOperationScope } from "@/hooks/useOperationScope";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { idSchema } from "@/lib/api/schemas";
import { getFeedback } from "@/lib/api/feedback";
export function useFeedbackResult() {
  const { scope, isActive, assertActive } = useOperationScope();
  const params = useSearchParams();
  const id = params.get("attemptId") ?? "";
  const evaluationId = params.get("evaluationId") ?? undefined;
  const valid =
    idSchema.safeParse(id).success &&
    (evaluationId === undefined || idSchema.safeParse(evaluationId).success);
  const query = useQuery({
    queryKey: [scope, "feedback", id, evaluationId ?? "latest"],
    queryFn: ({ signal }) => {
      assertActive();
      return getFeedback(id, signal, evaluationId);
    },
    enabled: isActive() && valid,
  });
  return {
    id,
    contextKey: `${id}:${evaluationId ?? "latest"}`,
    view: {
      loading: valid && query.isPending,
      error: !valid ? new Error("回答IDを確認してください。") : query.error,
    },
    feedback: query.data,
    actions: {
      refresh: () => {
        if (isActive()) void query.refetch();
      },
    },
  };
}
