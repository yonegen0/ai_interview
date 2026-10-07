/** @file usePracticeSession.ts @description State and side-effect controller for usePracticeSession. */
"use client";
import { useOperationScope } from "@/hooks/useOperationScope";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { idSchema } from "@/lib/api/schemas";
import { getQuestion } from "@/lib/api/interview";
import { getFeedback } from "@/lib/api/feedback";
export function usePracticeSession() {
  const { scope, isActive, assertActive } = useOperationScope();
  const params = useSearchParams();
  const id = params.get("sessionId") ?? "";
  const valid = idSchema.safeParse(id).success;
  const retryFrom =
    params.get("mode") === "retry" ? params.get("fromAttemptId") : null;
  const sourceEvaluation = params.get("fromEvaluationId") ?? undefined;
  const requestedEvaluation =
    params.get("mode") === "evaluation" ? params.get("evaluationId") : null;
  const origin = useQuery({
    queryKey: [scope, "feedback", retryFrom, sourceEvaluation ?? "latest"],
    queryFn: ({ signal }) => {
      assertActive();
      return getFeedback(retryFrom!, signal, sourceEvaluation);
    },
    enabled:
      isActive() &&
      !!retryFrom &&
      idSchema.safeParse(retryFrom).success &&
      (!sourceEvaluation || idSchema.safeParse(sourceEvaluation).success),
  });
  const query = useQuery({
    queryKey: [scope, "session", id],
    queryFn: ({ signal }) => {
      assertActive();
      return getQuestion(id, signal);
    },
    enabled: isActive() && valid,
  });
  if (!valid)
    return { view: { error: new Error("練習IDを確認してください。") } };
  if (
    requestedEvaluation !== null &&
    !idSchema.safeParse(requestedEvaluation).success
  )
    return { view: { error: new Error("評価IDを確認してください。") } };
  if (
    sourceEvaluation !== undefined &&
    !idSchema.safeParse(sourceEvaluation).success
  )
    return { view: { error: new Error("評価IDを確認してください。") } };
  if (query.isPending) return { view: { loading: "質問を読み込んでいます…" } };
  if (query.error)
    return {
      view: { error: query.error },
      refresh: () => {
        if (isActive()) void query.refetch();
      },
    };
  if (
    requestedEvaluation !== null &&
    query.data.activeAttempt?.evaluationId !== requestedEvaluation
  )
    return {
      view: {
        error: new Error(
          "練習が更新されています。現在の練習へ戻ってください。",
        ),
        returnUrl: `/practice/session/?sessionId=${id}`,
      },
    };
  if (params.get("mode") === "retry") {
    if (!retryFrom || !idSchema.safeParse(retryFrom).success)
      return {
        view: { error: new Error("再挑戦する回答IDを確認してください。") },
      };
    if (origin.isPending)
      return { view: { loading: "元の質問を確認しています…" } };
    if (origin.error)
      return {
        view: { error: origin.error },
        refresh: () => {
          if (isActive()) void origin.refetch();
        },
      };
    if (
      origin.data.sessionId !== id ||
      origin.data.questionNumber !== query.data.questionNumber ||
      query.data.activeAttempt?.attemptId !== retryFrom ||
      (sourceEvaluation &&
        query.data.activeAttempt.evaluationId !== sourceEvaluation)
    )
      return {
        view: {
          error: new Error(
            "練習が更新されています。現在の練習へ戻ってください。",
          ),
          returnUrl: `/practice/session/?sessionId=${id}`,
        },
      };
  }
  return {
    view: {},
    session: query.data,
    retryFrom,
    contextKey: `${id}:${query.data.questionNumber}:${retryFrom}:${query.data.activeAttempt?.evaluationId ?? "new"}`,
  };
}
