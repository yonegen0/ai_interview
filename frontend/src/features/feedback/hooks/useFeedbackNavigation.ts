/** @file useFeedbackNavigation.ts @description State and side-effect controller for useFeedbackNavigation. */
"use client";
import { useOperationScope } from "@/hooks/useOperationScope";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Feedback, Session } from "@/lib/api/schemas";
import { isFeedbackV2 } from "@/lib/api/schemas";
import { getQuestion, nextQuestion } from "@/lib/api/interview";
import { uncertain } from "@/lib/api/client";
import { operationSchema } from "@/lib/storage/recovery";
import type {
  FeedbackNavigationView,
  FeedbackNavigationActions,
} from "../model/navigation";
export function useFeedbackNavigation(feedback: Feedback) {
  const {
    scope,
    isActive,
    assertActive,
    storage: { readSaved, save, removeSaved },
  } = useOperationScope();
  const router = useRouter();
  const client = useQueryClient();
  const locked = useRef(false);
  const key = `pocket:next:${feedback.attemptId}`;
  const [initial] = useState(() => readSaved(key, operationSchema));
  const pending = useRef(initial);
  const [recovering, setRecovering] = useState(!!initial);
  const session = useQuery({
    queryKey: [scope, "session", feedback.sessionId],
    queryFn: ({ signal }) => {
      assertActive();
      return getQuestion(feedback.sessionId, signal);
    },
    enabled: isActive(),
    refetchOnMount: "always",
  });
  const mutation = useMutation({
    mutationFn: (requestKey: string) => {
      assertActive();
      return nextQuestion(feedback.sessionId, feedback.attemptId, requestKey);
    },
  });
  const current = (value?: Session) =>
    value?.questionNumber === feedback.questionNumber &&
    value.activeAttempt?.attemptId === feedback.attemptId &&
    value.activeAttempt.status === "completed" &&
    (!isFeedbackV2(feedback) ||
      (feedback.result.status === "completed" &&
        value.activeAttempt.evaluationId === feedback.evaluationId &&
        value.activeCoaching?.stage === "completed"));
  const canRetry = current(session.data) && !recovering && !mutation.isPending;
  const hasNext = session.data?.hasNext !== false;
  const next = async () => {
    if (
      !isActive() ||
      locked.current ||
      (!pending.current && (!current(session.data) || !hasNext))
    )
      return;
    locked.current = true;
    const operation = pending.current ?? {
      version: 1 as const,
      key: crypto.randomUUID(),
      fromAttemptId: feedback.attemptId,
    };
    pending.current = operation;
    save(key, operation);
    try {
      const value = await mutation.mutateAsync(operation.key);
      if (!isActive()) return;
      removeSaved(key);
      client.setQueryData([scope, "session", feedback.sessionId], value);
      router.push(`/practice/session/?sessionId=${feedback.sessionId}`);
    } catch (error) {
      if (!isActive()) return;
      if (uncertain(error)) setRecovering(true);
      else {
        pending.current = null;
        setRecovering(false);
        removeSaved(key);
        void session.refetch();
      }
    } finally {
      locked.current = false;
    }
  };

  return {
    view: {
      loading: session.isPending,
      error: session.error,
      mutationError: mutation.error,
      canRetry,
      canNext: (current(session.data) && hasNext) || recovering,
      hasNext,
      total: session.data?.totalQuestions,
      recovering,
      pending: mutation.isPending,
      sessionUrl: `/practice/session/?sessionId=${feedback.sessionId}`,
      retryUrl: `/practice/session/?sessionId=${feedback.sessionId}&mode=retry&fromAttemptId=${feedback.attemptId}${isFeedbackV2(feedback) ? `&fromEvaluationId=${feedback.evaluationId}` : ""}`,
    } satisfies FeedbackNavigationView,
    actions: {
      next,
      refresh: () => {
        if (isActive()) void session.refetch();
      },
    } satisfies FeedbackNavigationActions,
  };
}
