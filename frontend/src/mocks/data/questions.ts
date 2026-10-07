/** @file questions.ts @description Shared canonical bank and legacy mock recovery assets. */
import defaults from "../../../../backend/src/interview_backend/assets/questions.json";
import legacy from "./legacy-questions.json";
import { questionSchema, managedQuestionSchema } from "@/lib/api/schemas";
export const questions = defaults.map((value) =>
  managedQuestionSchema.parse(value),
);
export const legacyQuestions = legacy.map((value) =>
  questionSchema.parse(value),
);
