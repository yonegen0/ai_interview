/** @file practice.ts @description Typed view models and validation for practice. */
import type { FormEventHandler } from "react";
import type { UseFormRegisterReturn } from "react-hook-form";
import type { Session } from "@/lib/api/schemas";
import type { Phase } from "./machine";
/** Explain the existing exit behavior without changing storage or navigation. */
export function exitNotice(phase: Phase): string {
  switch (phase) {
    case "answering":
      return "入力中の下書きは破棄されます。";
    case "submitting":
      return "送信結果はまだ確定していません。送信内容を保持して終了します。送信処理は取り消されません。";
    case "recovery_required":
      return "送信結果を確認できていません。送信内容を保持して終了し、元の練習で結果を再確認できます。";
    case "processing":
    case "completed":
      return "送信済みの評価は中止されません。";
    case "failed":
      return "練習画面を離れます。";
  }
}
export type AnswerSubmissionProps = {
  field: UseFormRegisterReturn;
  count: number;
  phase: Phase;
  valid: boolean;
  inputError?: string;
  error: Error | null;
  onSubmit: FormEventHandler<HTMLFormElement>;
  onReconfirm: () => void;
};
export type PracticeView = {
  session: Session;
  phase: Phase;
  confirm: boolean;
  elapsed: number;
  paused: boolean;
  evaluationError: Error | null;
  longWaitSeconds?: number;
};
export type PracticeActions = {
  retry: () => void;
  refreshEvaluation: () => void;
  requestExit: () => void;
  closeExit: () => void;
  exit: () => void;
};
