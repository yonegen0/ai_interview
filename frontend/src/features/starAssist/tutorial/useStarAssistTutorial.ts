/** @file useStarAssistTutorial.ts @description 12ステップと完了状態を固定教材から一意に導出する。 */
"use client";

import { useCallback, useMemo, useState } from "react";
import type { StarInput } from "@/lib/api/schemas/star";
import {
  TUTORIAL_CANDIDATES,
  TUTORIAL_CATEGORY,
  TUTORIAL_EDITED_A,
  TUTORIAL_NOTES,
  TUTORIAL_STEP_DESCRIPTIONS,
} from "./tutorialData";

export const TUTORIAL_STEP_COUNT = 12;
export const TUTORIAL_COMPLETE_STEP = 13;
export type TutorialHighlight =
  | "S" | "T" | "A" | "R" | "category" | "generate"
  | "A" | "B" | "C" | "edit" | "apply" | null;

export type TutorialView = {
  step: number;
  completed: boolean;
  notes: StarInput["notes"];
  targetCategory: typeof TUTORIAL_CATEGORY | null;
  candidatesVisible: boolean;
  selectedCandidate: "A" | "B" | "C" | null;
  editing: boolean;
  edited: boolean;
  answer: string;
  highlight: TutorialHighlight;
  description: string;
};

export function getTutorialView(step: number): TutorialView {
  const current = Number.isFinite(step)
    ? Math.max(1, Math.min(TUTORIAL_COMPLETE_STEP, Math.trunc(step)))
    : 1;
  const notes: StarInput["notes"] = {
    S: current >= 2 ? TUTORIAL_NOTES.S : "",
    T: current >= 3 ? TUTORIAL_NOTES.T : "",
    A: current >= 4 ? TUTORIAL_NOTES.A : "",
    R: current >= 5 ? TUTORIAL_NOTES.R : "",
  };
  const selectedCandidate = current < 7 ? null
    : current === 8 ? "B" : current === 9 ? "C" : "A";
  // Highlight the value that *just* appeared, not the next empty field.
  const highlight: TutorialHighlight = current <= 5
    ? (["S", "S", "T", "A", "R"] as const)[current - 1]
    : current === 6 ? "category"
        : current <= 9 ? selectedCandidate
          : current <= 11 ? "edit"
            : current === 12 ? "apply" : null;
  return {
    step: current,
    completed: current === TUTORIAL_COMPLETE_STEP,
    notes,
    targetCategory: current >= 6 ? TUTORIAL_CATEGORY : null,
    candidatesVisible: current >= 7 && current <= 12,
    selectedCandidate,
    editing: current === 11 || current === 12,
    edited: current >= 12,
    answer: current === TUTORIAL_COMPLETE_STEP ? TUTORIAL_EDITED_A : "",
    highlight,
    description: current === TUTORIAL_COMPLETE_STEP
      ? "チュートリアル完了！"
      : TUTORIAL_STEP_DESCRIPTIONS[current - 1],
  };
}

export function useStarAssistTutorial(onClose: () => void) {
  const [step, setStep] = useState(1);
  const next = useCallback(() => {
    setStep((value) => Math.min(TUTORIAL_COMPLETE_STEP, value + 1));
  }, []);
  const back = useCallback(() => {
    setStep((value) => Math.max(1, value - 1));
  }, []);
  const reset = useCallback(() => setStep(1), []);
  const close = useCallback(() => {
    setStep(1);
    onClose();
  }, [onClose]);
  const view = useMemo(() => getTutorialView(step), [step]);
  return { step, next, back, reset, close, view, candidates: TUTORIAL_CANDIDATES };
}
