/** @file useAnswerOperation.ts @description 回答の単一送信・永続化・復旧・評価統合 */
"use client";
import { useOperationScope } from "@/hooks/useOperationScope";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  formSchema,
  type Session,
  type Attempt,
  type V2Answer,
} from "@/lib/api/schemas";
import { submitAnswer } from "@/lib/api/interview";
import { uncertain } from "@/lib/api/client";
import { answerRecoverySchema } from "@/lib/storage/recovery";
import { reducer, type Phase } from "@/lib/answerMachine";
import { useEvaluation } from "@/hooks/useEvaluation";
import type { EvaluationTiming } from "@/hooks/useEvaluation";
/** 保存済み要求の手動確認と、同じ質問への再入力を復元する。 */
export const useAnswerOperation = (
  session: Session,
  retryFrom: string | null,
  timing?: EvaluationTiming,
  operation?: Extract<V2Answer, { kind: "coaching_answer" }>,
  onAccepted?: (result: Attempt) => void,
) => {
  const {
    isActive,
    scope,
    assertActive,
    storage: { readSaved, save, removeSaved },
  } = useOperationScope();
  const client = useQueryClient();
  const storageKey = `pocket:answer:${session.sessionId}`;
  const legacyContext = `${session.questionNumber}:${retryFrom ?? "normal"}`;
  const context = `${legacyContext}:${operation?.kind ?? "initial"}:${operation?.fromEvaluationId ?? "new"}`;
  const [saved] = useState(() => {
    const value = readSaved(storageKey, answerRecoverySchema);
    return value?.questionId === session.question.id &&
      (value.context === context ||
        (value.version === 1 &&
          !operation &&
          value.context === legacyContext) ||
        (value.version === 2 &&
          value.pending &&
          value.context.startsWith(`${session.questionNumber}:`)))
      ? value
      : null;
  });
  const [attempt, setAttempt] = useState<Attempt | null>(() =>
    operation ||
    saved?.pending ||
    retryFrom === session.activeAttempt?.attemptId ||
    (saved &&
      session.activeAttempt?.status === "failed" &&
      !session.activeCoaching)
      ? null
      : session.activeAttempt,
  );
  const [phase, dispatch] = useReducer(
    reducer,
    (attempt
      ? "processing"
      : saved?.pending
        ? "recovery_required"
        : "answering") as Phase,
  );
  const pending = useRef(saved?.pending);
  const isInitialOperation = operation === undefined;
  const removeOwnedRecovery = useCallback(() => {
    const value = readSaved(storageKey, answerRecoverySchema);
    if (
      value?.questionId === session.question.id &&
      (value.pending
        ? value.pending.key === pending.current?.key
        : value.context === context ||
          (value.version === 1 &&
            isInitialOperation &&
            value.context === legacyContext))
    )
      removeSaved(storageKey);
  }, [
    readSaved,
    storageKey,
    session.question.id,
    context,
    isInitialOperation,
    legacyContext,
    removeSaved,
  ]);
  const locked = useRef(false);
  const [error, setError] = useState<Error | null>(null);
  const form = useForm<{ answer: string }>({
    resolver: zodResolver(formSchema),
    mode: "onChange",
    defaultValues: {
      answer:
        saved?.pending && "answer" in saved.pending.body
          ? saved.pending.body.answer
          : (saved?.draft ?? ""),
    },
  });
  const answer = useWatch({ control: form.control, name: "answer" }) ?? "";
  const evaluation = useEvaluation(attempt?.evaluationId, timing);
  const mutation = useMutation({
    retry: false,
    mutationFn: (value: NonNullable<typeof pending.current>) => {
      assertActive();
      return submitAnswer(session.sessionId, value.body, value.key);
    },
  });
  useEffect(() => {
    if (isActive() && phase === "answering")
      save(storageKey, {
        version: 2,
        questionId: session.question.id,
        context,
        draft: answer,
      });
  }, [answer, phase, storageKey, context, session.question.id, save, isActive]);
  useEffect(() => {
    if (!isActive()) return;
    if (evaluation.data?.status === "completed") {
      dispatch("COMPLETE");
      removeOwnedRecovery();
      void client.invalidateQueries({
        queryKey: [scope, "session", session.sessionId],
      });
    }
    if (evaluation.data?.status === "failed") {
      dispatch("FAIL");
      removeOwnedRecovery();
      void client.invalidateQueries({
        queryKey: [scope, "session", session.sessionId],
      });
    }
  }, [
    evaluation.data,
    removeOwnedRecovery,
    isActive,
    client,
    scope,
    session.sessionId,
  ]);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (answer || pending.current || phase === "processing") {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [answer, phase]);
  const send = async (value?: { answer: string }) => {
    if (
      !isActive() ||
      locked.current ||
      (!["answering", "recovery_required"].includes(phase) &&
        !(
          phase === "failed" &&
          pending.current &&
          "kind" in pending.current.body &&
          pending.current.body.kind === "retry_evaluation"
        ))
    )
      return;
    locked.current = true;
    setError(null);
    const payload = pending.current ?? {
      key: crypto.randomUUID(),
      body: operation
        ? { ...operation, answer: value?.answer ?? answer }
        : retryFrom && session.activeAttempt
          ? {
              kind: "retry_attempt" as const,
              questionId: session.question.id,
              answer: value?.answer ?? answer,
              fromAttemptId: retryFrom,
              fromEvaluationId: session.activeAttempt.evaluationId,
            }
          : {
              kind: "initial_answer" as const,
              questionId: session.question.id,
              answer: value?.answer ?? answer,
            },
    };
    pending.current = payload;
    save(storageKey, {
      version: 2,
      questionId: session.question.id,
      context,
      draft: "answer" in payload.body ? payload.body.answer : answer,
      pending: payload,
    });
    dispatch("SUBMIT");
    try {
      const result = await mutation.mutateAsync(payload);
      if (!isActive()) return;
      setAttempt(result);
      onAccepted?.(result);
      void client.invalidateQueries({
        queryKey: [scope, "session", session.sessionId],
      });
      removeOwnedRecovery();
      pending.current = undefined;
      dispatch("ACCEPT");
    } catch (cause) {
      if (!isActive()) return;
      const failure =
        cause instanceof Error ? cause : new Error("送信できませんでした。");
      setError(failure);
      if (uncertain(cause)) dispatch("UNKNOWN");
      else {
        removeOwnedRecovery();
        pending.current = undefined;
        dispatch(
          payload.body.kind === "retry_evaluation"
            ? "RETRY_REJECTED"
            : "INVALID",
        );
        void client.invalidateQueries({
          queryKey: [scope, "session", session.sessionId],
        });
      }
    } finally {
      locked.current = false;
    }
  };
  const retry = () => {
    if (!isActive()) return;
    if (
      attempt &&
      (evaluation.data?.feedbackVersion === 2 || session.activeCoaching)
    ) {
      pending.current = {
        key: crypto.randomUUID(),
        body: {
          kind: "retry_evaluation",
          attemptId: attempt.attemptId,
          fromEvaluationId: attempt.evaluationId,
        },
      };
      void send();
      return;
    }
    pending.current = undefined;
    setAttempt(null);
    form.reset({ answer: "" });
    setError(null);
    dispatch("RETRY");
  };
  return {
    form,
    answer,
    phase,
    error,
    evaluation,
    attempt,
    send,
    retry,
    discard: () => {
      if (isActive()) removeOwnedRecovery();
    },
  };
};
