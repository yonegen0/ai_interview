/** @file editor.ts @description Typed view models and validation for editor. */
import { z } from "zod";
import type { Control, FieldErrors, FieldArrayWithId } from "react-hook-form";
import type { FormEventHandler } from "react";
import {
  bankSaveSchema,
  bankSchema,
  idSchema,
  managedQuestionSchema,
  type BankSave,
  type QuestionBank,
} from "@/lib/api/schemas";
const draftQuestion = managedQuestionSchema
  .extend({ question: z.string() })
  .strip();
export const savedBankSchema = z.object({
  baseline: bankSchema,
  draft: z.object({
    expectedVersion: bankSaveSchema.shape.expectedVersion,
    questions: z.array(draftQuestion).max(100),
  }),
  pending: z.object({ key: idSchema, body: bankSaveSchema }).optional(),
});
export type Stage =
  | "editable"
  | "confirm"
  | "saving"
  | "uncertain"
  | "conflict"
  | "forbidden"
  | "success";
export const storageKey = "pocket:admin:question-bank";

export const stageReducer = (_state: Stage, next: Stage): Stage => next;
export function changeSummary(
  current: BankSave["questions"],
  old: BankSave["questions"],
) {
  const before = new Map(old.map((q, i) => [q.id, { q, i }]));
  const after = new Map(current.map((q) => [q.id, q]));
  return {
    added: current.filter((q) => !before.has(q.id)).length,
    removed: old.filter((q) => !after.has(q.id)).length,
    edited: current.filter(
      (q) =>
        before.has(q.id) &&
        JSON.stringify(before.get(q.id)!.q) !== JSON.stringify(q),
    ).length,
    moved: current.filter(
      (q, i) => before.has(q.id) && before.get(q.id)!.i !== i,
    ).length,
  };
}
export type ChangeSummary = ReturnType<typeof changeSummary>;
export type EditorBindings = {
  control: Control<BankSave>;
  fields: FieldArrayWithId<BankSave, "questions", "fieldKey">[];
  errors: FieldErrors<BankSave>;
};
export type ManagementView = {
  initialized: boolean;
  loading: boolean;
  stage: Stage;
  error: Error | null;
  message: string;
  changed: boolean;
  disabled: boolean;
  canConfirm: boolean;
  questions: BankSave["questions"];
  comparison: QuestionBank | null;
  previousDraft: BankSave | null;
  preview: boolean;
  summary: ChangeSummary;
};
export type ManagementActions = {
  confirm: FormEventHandler<HTMLFormElement>;
  publish: () => Promise<void>;
  back: () => void;
  cancel: () => void;
  togglePreview: () => void;
  refresh: () => void;
  fetchLatest: () => Promise<void>;
  adoptLatest: () => void;
  appendQuestion: () => void;
  removeQuestion: (index: number) => void;
  moveQuestion: (index: number, direction: -1 | 1) => void;
};
