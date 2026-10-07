/** @file useQuestionBankEditor.ts @description State and side-effect controller for useQuestionBankEditor. */
"use client";
import { useForm, useWatch, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  bankSaveSchemaForBaseline,
  type BankSave,
  type QuestionBank,
} from "@/lib/api/schemas";
export function useQuestionBankEditor(baseline: BankSave["questions"] = []) {
  const form = useForm<BankSave>({
    resolver: zodResolver(bankSaveSchemaForBaseline(baseline)),
    defaultValues: { expectedVersion: 0, questions: [] },
    mode: "onChange",
  });
  const { fields, append, remove, move } = useFieldArray({
    control: form.control,
    name: "questions",
    keyName: "fieldKey",
  });
  const draft = useWatch({ control: form.control });
  return {
    form,
    fields,
    draft,
    appendQuestion: () =>
      append({
        id: crypto.randomUUID(),
        category: "self_introduction",
        difficulty: "standard",
        question: "",
      }),
    removeQuestion: remove,
    moveQuestion: (index: number, direction: -1 | 1) => {
      const target = index + direction;
      if (target >= 0 && target < fields.length) move(index, target);
    },
    resetEditor: (bank: QuestionBank) =>
      form.reset({
        expectedVersion: bank.version,
        questions: structuredClone(bank.questions),
      }),
  };
}
