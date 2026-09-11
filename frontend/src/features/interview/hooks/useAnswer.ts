/** @file useAnswer.ts @description 回答の単一送信・永続化・復旧・評価統合 */
"use client";
import { useEffect, useReducer, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { formSchema, type Session, type Attempt } from "@/lib/api/schemas";
import { submitAnswer } from "@/lib/api/interview";
import { uncertain } from "@/lib/api/client";
import {
  readSaved,
  recoverySchema,
  removeSaved,
  save,
} from "@/lib/storage/recovery";
import { reducer, type Phase } from "@/features/interview/model/machine";
import { useEvaluation } from "@/features/interview/hooks/useEvaluation";
import type { EvaluationTiming } from "@/features/interview/hooks/useEvaluation";
/** 保存済み要求の手動確認と、同じ質問への再入力を復元する。 */
export const useAnswer = (
  session: Session,
  retryFrom: string | null,
  timing?: EvaluationTiming,
) => {
  const storageKey = `pocket:answer:${session.sessionId}`;
  const context = `${session.questionNumber}:${retryFrom ?? "normal"}`;
  const [saved] = useState(() => {
    const value = readSaved(storageKey, recoverySchema);
    return value?.questionId === session.question.id &&
      value.context === context
      ? value
      : null;
  });
  const [attempt, setAttempt] = useState<Attempt | null>(() =>
    saved?.pending ||
    retryFrom === session.activeAttempt?.attemptId ||
    (saved && session.activeAttempt?.status === "failed")
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
  const locked = useRef(false);
  const [error, setError] = useState<Error | null>(null);
  const form = useForm<{ answer: string }>({
    resolver: zodResolver(formSchema),
    mode: "onChange",
    defaultValues: {
      answer: saved?.pending?.body.answer ?? saved?.draft ?? "",
    },
  });
  const answer = useWatch({ control: form.control, name: "answer" }) ?? "";
  const evaluation = useEvaluation(attempt?.evaluationId, timing);
  const mutation = useMutation({
    mutationFn: (value: NonNullable<typeof pending.current>) =>
      submitAnswer(session.sessionId, value.body, value.key),
  });
  useEffect(() => {
    if (phase === "answering")
      save(storageKey, {
        version: 1,
        questionId: session.question.id,
        context,
        draft: answer,
      });
  }, [answer, phase, storageKey, context, session.question.id]);
  useEffect(() => {
    if (evaluation.data?.status === "completed") {
      dispatch("COMPLETE");
      removeSaved(storageKey);
    }
    if (evaluation.data?.status === "failed") {
      dispatch("FAIL");
      removeSaved(storageKey);
    }
  }, [evaluation.data, storageKey]);
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
    if (locked.current || !["answering", "recovery_required"].includes(phase))
      return;
    locked.current = true;
    setError(null);
    const payload = pending.current ?? {
      key: crypto.randomUUID(),
      body: {
        questionId: session.question.id,
        answer: value?.answer ?? answer,
      },
    };
    pending.current = payload;
    save(storageKey, {
      version: 1,
      questionId: session.question.id,
      context,
      draft: payload.body.answer,
      pending: payload,
    });
    dispatch("SUBMIT");
    try {
      const result = await mutation.mutateAsync(payload);
      setAttempt(result);
      pending.current = undefined;
      removeSaved(storageKey);
      dispatch("ACCEPT");
    } catch (cause) {
      const failure =
        cause instanceof Error ? cause : new Error("送信できませんでした。");
      setError(failure);
      if (uncertain(cause)) dispatch("UNKNOWN");
      else {
        pending.current = undefined;
        dispatch("INVALID");
      }
    } finally {
      locked.current = false;
    }
  };
  const retry = () => {
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
    send,
    retry,
    discard: () => removeSaved(storageKey),
  };
};
