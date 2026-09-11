/** @file AnswerField.tsx @description 回答入力と文字数・エラー表示をまとめるMolecule。 */
"use client";
import type { UseFormRegisterReturn } from "react-hook-form";
import { Input } from "@/components/atoms/Input";
export const AnswerField = ({
  field,
  count,
  disabled,
  error,
}: {
  field: UseFormRegisterReturn;
  count: number;
  disabled?: boolean;
  error?: string;
}) => {
  const { ref, ...registration } = field;
  return (
    <Input
      {...registration}
      inputRef={ref}
      label="あなたの回答"
      multiline
      minRows={6}
      disabled={disabled}
      error={!!error}
      helperText={error ?? `${count} / 2000文字 · 100〜300文字がおすすめです`}
      slotProps={{ formHelperText: { "aria-live": "polite" } }}
    />
  );
};
