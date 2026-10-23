/** @file StarFields.tsx @description STARメモと選択前から編集できる各案。 */
"use client";
import { styled } from "@mui/material/styles";
import { Input } from "@/components/atoms/Input";
import { Text } from "@/components/atoms/Text";
import type { UseFormReturn } from "react-hook-form";
import type { StarInput } from "@/lib/api/schemas/star";
const Fields = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  marginBlock: theme.spacing(2),
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
}: {
  form: UseFormReturn<StarInput>;
  input: StarInput;
  disabled: boolean;
}) {
  return (
    <Fields>
      {input.candidates.map((candidate, index) => (
        <div key={candidate.id}>
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
            error={Array.from(candidate.text).length > 400}
            helperText={`${Array.from(candidate.text).length} / 400文字。選択前から編集できます。`}
          />
        </div>
      ))}
    </Fields>
  );
}
