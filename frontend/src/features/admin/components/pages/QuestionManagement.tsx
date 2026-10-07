/** @file QuestionManagement.tsx @description Presentation and composition for QuestionManagement. */
"use client";
import { useQuestionManagement } from "../../hooks/useQuestionManagement";
import { QuestionManagementTemplate } from "../templates/QuestionManagementTemplate";
export const QuestionManagement = () => (
  <QuestionManagementTemplate {...useQuestionManagement()} />
);
