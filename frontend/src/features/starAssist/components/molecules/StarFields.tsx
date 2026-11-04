/** @file StarFields.tsx @description STARメモと選択前から編集できる各案。 */
"use client";
import { styled } from "@mui/material/styles";
import { Input } from "@/components/atoms/Input";
import { Text } from "@/components/atoms/Text";
import type { UseFormReturn } from "react-hook-form";
import {
  countStarText, STAR_OUTPUT_LIMIT, OTHER_ASSIST_OUTPUT_LIMIT,
  type StarInput, type AssistMode,
} from "@/lib/api/schemas/star";
const Fields = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  marginBlock: theme.spacing(2),
}));
const CandidateField = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1),
}));
export function StarNotesFields({
  form,
  disabled,
}: {
  form: UseFormReturn<StarInput>;
  disabled: boolean;
}) {
  return (
    <Fields>
      {(["S", "T", "A", "R"] as const).map((key) => (
        <Input
          key={key}
          {...form.register(`notes.${key}`)}
          label={
            { S: "S 状況", T: "T 課題・役割", A: "A 本人の行動", R: "R 結果" }[
              key
            ]
          }
          multiline
          minRows={2}
          disabled={disabled}
          error={!!form.formState.errors.notes?.[key]}
          helperText={
            form.formState.errors.notes?.[key]?.message ??
            "任意。経験した事実だけを入力してください。"
          }
        />
      ))}
    </Fields>
  );
}
export function StarCandidateFields({
  form,
  input,
  disabled,
  mode = "star",
}: {
  form: UseFormReturn<StarInput>;
  input: StarInput;
  disabled: boolean;
  mode?: AssistMode;
}) {
  const maximum = mode === "star" ? STAR_OUTPUT_LIMIT : OTHER_ASSIST_OUTPUT_LIMIT;
  const length = (text: string) => mode === "star" ? countStarText(text) : text.length;
  const unit = mode === "star" ? "文字" : "UTF-16単位（絵文字などは2単位）";
  return (
    <Fields>
      {input.candidates.map((candidate, index) => (
        <CandidateField key={candidate.id}>
          <Text variant="h3" component="h3">
            {candidate.id} —{" "}
            {
              {
                conclusion: "結論重視",
                action: "行動重視",
                conversational: "会話重視",
              }[candidate.style]
            }
          </Text>
          <Input
            {...form.register(`candidates.${index}.text`)}
            label={`案${candidate.id}の回答`}
            multiline
            minRows={4}
            disabled={disabled}
            error={length(candidate.text) > maximum}
            helperText={`${length(candidate.text)} / ${maximum} ${unit}。選択前から編集できます。`}
          />
        </CandidateField>
      ))}
    </Fields>
  );
}
