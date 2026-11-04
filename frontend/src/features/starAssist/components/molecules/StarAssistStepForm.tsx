/** @file StarAssistStepForm.tsx @description 選択中のSTARメモ入力とSchema由来のエラー表示。 */
"use client";

import FlagOutlinedIcon from "@mui/icons-material/FlagOutlined";
import { styled } from "@mui/material/styles";
import { useRef, useState } from "react";
import { Controller, type UseFormReturn } from "react-hook-form";
import { Input } from "@/components/atoms/Input";
import { Text } from "@/components/atoms/Text";
import { STAR_INPUT_LIMIT, countStarText, countStarNotes, starNotesSchema, type StarInput } from "@/lib/api/schemas/star";
import { starSteps, type AssistStep } from "../../model/steps";
import type { AssistMode } from "@/lib/api/schemas/star";

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
  mode = "star",
  steps = starSteps,
}: {
  step: number;
  form: UseFormReturn<StarInput>;
  input: StarInput;
  disabled: boolean;
  mode?: AssistMode;
  steps?: readonly AssistStep[];
}) {
  const current = steps[step] ?? steps[0];
  const text = input.notes[current.key];
  const count = countStarText(text);
  const [warning, setWarning] = useState(false);
  const composing = useRef(false);
  const parsed = starNotesSchema.shape[current.key].safeParse(text);
  const error = form.formState.errors.notes?.[current.key]?.message ??
    (parsed.success ? null : parsed.error.issues[0]?.message);
  const label = mode === "star" && current.key === "A" ? "A 本人の行動" : current.label;
  return (
    <FormCard aria-label={current.label + "の入力"}>
      <Heading>
        <FlagOutlinedIcon fontSize="large" aria-hidden="true" />
        <Text variant="h2" component="h2">
          {current.label}（{current.english}）
        </Text>
      </Heading>
      <Text variant="body2" color="text.secondary">{current.description}</Text>
      <Controller
        key={current.key}
        name={`notes.${current.key}`}
        control={form.control}
        render={({ field }) => (
          <Input
            {...field}
            label={label}
            multiline
            minRows={5}
            placeholder={current.placeholder}
            disabled={disabled}
            error={!!error || warning}
            helperText={warning && mode === "star"
              ? "STARアシストは4項目の合計600文字まで入力できます。内容を短くしてください。"
              : error || "任意。実際の経験や考えだけを箇条書きで入力してください。"}
            onCompositionStart={() => { composing.current = true; }}
            onCompositionEnd={(event) => {
              composing.current = false;
              // Keep the committed IME text untrimmed even on overflow.
              field.onChange((event.target as HTMLInputElement).value);
              setWarning(mode === "star" && countStarNotes({
                ...form.getValues("notes"),
                [current.key]: (event.target as HTMLInputElement).value,
              }) > STAR_INPUT_LIMIT);
            }}
            onChange={(event) => {
              const next = event.target.value;
              const notes = form.getValues("notes");
              const oldCount = countStarNotes(notes);
              const newCount = countStarNotes({ ...notes, [current.key]: next });
              if (composing.current) {
                field.onChange(next);
              } else if (mode === "star" && newCount > STAR_INPUT_LIMIT && newCount > oldCount) {
                setWarning(true);
              } else {
                field.onChange(next);
                setWarning(false);
              }
            }}
          />
        )}
      />
      <Count>
        <Text variant="caption" color={error ? "error.main" : "text.secondary"}>
          {count}文字入力
        </Text>
      </Count>
    </FormCard>
  );
}
