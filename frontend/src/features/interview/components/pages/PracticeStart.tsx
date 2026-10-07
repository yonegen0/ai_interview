/** @file PracticeStart.tsx @description Presentation and composition for PracticeStart. */
"use client";
import { usePracticeStart } from "../../hooks/usePracticeStart";
import { PracticeStartTemplate } from "../templates/PracticeStartTemplate";
export const PracticeStart = () => (
  <PracticeStartTemplate {...usePracticeStart()} />
);
