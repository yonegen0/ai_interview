/** @file usePracticeController.ts @description State and side-effect controller for usePracticeController. */
"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useOperationScope } from "@/hooks/useOperationScope";
import type { Session } from "@/lib/api/schemas";
import { useAnswer } from "./useAnswer";
import type { EvaluationTiming } from "./useEvaluation";
import type {
  PracticeView,
  PracticeActions,
  AnswerSubmissionProps,
} from "../model/practice";
export function usePracticeController(
  session: Session,
  retryFrom: string | null,
  timing?: EvaluationTiming,
) {
  const { isActive } = useOperationScope();
  const state = useAnswer(session, retryFrom, timing);
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const navigated = useRef<string | null>(null);
  useEffect(() => {
    if (!isActive()) return;
    const data = state.evaluation.data;
    if (data?.status === "completed" && navigated.current !== data.attemptId) {
      navigated.current = data.attemptId;
      router.push(`/result/?attemptId=${data.attemptId}`);
    }
  }, [state.evaluation.data, router, isActive]);
  const exit = () => {
    if (!isActive()) return;
    state.discard();
    router.push("/practice/");
  };
  return {
    view: {
      session,
      phase: state.phase,
      confirm,
      elapsed: state.evaluation.elapsed,
      paused: state.evaluation.paused,
      evaluationError: state.evaluation.error,
      longWaitSeconds: timing?.longWaitSeconds,
    } satisfies PracticeView,
    form: {
      field: state.form.register("answer"),
      count: state.answer.length,
      phase: state.phase,
      valid: state.form.formState.isValid,
      inputError: state.form.formState.errors.answer?.message,
      error: state.error,
      onSubmit: state.form.handleSubmit((value) => state.send(value)),
      onReconfirm: () => {
        void state.send();
      },
    } satisfies AnswerSubmissionProps,
    actions: {
      retry: state.retry,
      refreshEvaluation: () => {
        if (isActive()) void state.evaluation.refetch();
      },
      requestExit: () => {
        if (state.answer || state.phase !== "answering") setConfirm(true);
        else exit();
      },
      closeExit: () => setConfirm(false),
      exit,
    } satisfies PracticeActions,
  };
}
