/** @file PracticeSessionContent.tsx @description Presentation and composition for PracticeSessionContent. */
"use client";
import type { Session } from "@/lib/api/schemas";
import { usePracticeController } from "../../hooks/usePracticeController";
import type { EvaluationTiming } from "../../hooks/useEvaluation";
import { PracticeForm } from "../templates/PracticeForm";
export type PracticeSessionContentProps = {
  session: Session;
  retryFrom: string | null;
  timing?: EvaluationTiming;
  previousAnswer?: string;
};
export const PracticeSessionContent = ({
  session,
  retryFrom,
  timing,
  previousAnswer,
}: PracticeSessionContentProps) => (
  <PracticeForm
    {...usePracticeController(session, retryFrom, timing, previousAnswer)}
  />
);
