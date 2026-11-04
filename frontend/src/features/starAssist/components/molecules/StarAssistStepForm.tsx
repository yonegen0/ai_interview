/** @file StarAssistStepForm.tsx @description 選択中のSTARメモ入力とSchema由来のエラー表示。 */
"use client";

import FlagOutlinedIcon from "@mui/icons-material/FlagOutlined";
import { styled } from "@mui/material/styles";
import type { UseFormReturn } from "react-hook-form";
import { Input } from "@/components/atoms/Input";
import { Text } from "@/components/atoms/Text";
import { starNotesSchema, type StarInput } from "@/lib/api/schemas/star";
import { starSteps } from "../../model/steps";

const FormCard = styled("section")(({ theme }) => ({
  minWidth: 0,
  border: "1px solid " + theme.palette.divider,
  borderRadius: theme.shape.borderRadius,
  padding: theme.spacing(3),
  display: "grid",
  alignContent: "start",
  gap: theme.spacing(2),
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(2) },
}));
const Heading = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1.5),
  "& svg": { color: theme.palette.primary.main, flexShrink: 0 },
}));
const Count = styled("div")(() => ({ textAlign: "right" }));

export function StarAssistStepForm({
  step,
  form,
  input,
  disabled,
}: {
  step: number;
  form: UseFormReturn<StarInput>;
  input: StarInput;
  disabled: boolean;
}) {
  const current = starSteps[step] ?? starSteps[0];
  const text = input.notes[current.key];
  const count = Array.from(text).length;
  const parsed = starNotesSchema.shape[current.key].safeParse(text);
  const error = form.formState.errors.notes?.[current.key]?.message ??
    (parsed.success ? null : parsed.error.issues[0]?.message);
  const label = current.key === "A" ? "A 本人の行動" : current.key + " " + current.label;
  return (
    <FormCard aria-label={current.label + "の入力"}>
      <Heading>
        <FlagOutlinedIcon fontSize="large" aria-hidden="true" />
        <Text variant="h2" component="h2">
          {current.label}（{current.english}）
        </Text>
      </Heading>
      <Text variant="body2" color="text.secondary">{current.description}</Text>
      <Input
        key={current.key}
        {...form.register(`notes.${current.key}`)}
        defaultValue={text}
        label={label}
        multiline
        minRows={5}
        placeholder={current.placeholder}
        disabled={disabled}
        error={!!error}
        helperText={error || "任意。経験した事実だけを入力してください。"}
      />
      <Count>
        <Text variant="caption" color={error ? "error.main" : "text.secondary"}>
          {count}文字入力
        </Text>
      </Count>
    </FormCard>
  );
}
