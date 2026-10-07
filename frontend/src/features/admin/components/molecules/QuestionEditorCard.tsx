/** @file QuestionEditorCard.tsx @description Presentation and composition for QuestionEditorCard. */
"use client";
import { Controller, type Control, type FieldErrors } from "react-hook-form";
import { styled } from "@mui/material/styles";
import { Panel } from "@/components/atoms/Panel";
import { Input } from "@/components/atoms/Input";
import { Select } from "@/components/atoms/Select";
import { Text } from "@/components/atoms/Text";
import { Button } from "@/components/atoms/Button";
import { Actions } from "@/components/atoms/Actions";
import {
  activeCategoryIds,
  categories,
  type BankSave,
} from "@/lib/api/schemas";
const options = activeCategoryIds.map((value) => ({
  value,
  label: categories[value],
}));
const Fields = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  marginTop: theme.spacing(2),
}));
export type QuestionEditorCardProps = {
  index: number;
  fieldKey: string;
  control: Control<BankSave>;
  errors: FieldErrors<BankSave>;
  disabled: boolean;
  first: boolean;
  last: boolean;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
};
export function QuestionEditorCard({
  index,
  fieldKey,
  control,
  errors,
  disabled,
  first,
  last,
  onMove,
  onRemove,
}: QuestionEditorCardProps) {
  const error = errors.questions?.[index];
  return (
    <Panel>
      <Text variant="h2" component="h2">
        質問 {index + 1}
      </Text>
      <Fields>
        <Controller
          control={control}
          name={`questions.${index}.question`}
          render={({ field: { ref, ...field } }) => (
            <Input
              {...field}
              inputRef={ref}
              id={`question-${fieldKey}`}
              label="質問本文"
              multiline
              minRows={4}
              disabled={disabled}
              error={!!error?.question}
              helperText={
                error?.question
                  ? "質問本文は空白以外で1〜1,000文字にしてください。"
                  : `${field.value.length} / 1,000文字`
              }
              slotProps={{
                formHelperText: {
                  "aria-live": "polite",
                  role: error?.question ? "alert" : undefined,
                },
              }}
            />
          )}
        />
        <Controller
          control={control}
          name={`questions.${index}.category`}
          render={({ field: { ref, ...field } }) => (
            <Select
              {...field}
              inputRef={ref}
              id={`category-${fieldKey}`}
              label="カテゴリ"
              options={options}
              disabled={disabled}
              fullWidth
              error={error?.category?.message}
            />
          )}
        />
      </Fields>
      <Actions>
        <Button
          variant="outlined"
          color="primary"
          type="button"
          disabled={disabled || first}
          aria-label={`質問${index + 1}を上へ`}
          onClick={() => onMove(-1)}
        >
          上へ
        </Button>
        <Button
          variant="outlined"
          color="primary"
          type="button"
          disabled={disabled || last}
          aria-label={`質問${index + 1}を下へ`}
          onClick={() => onMove(1)}
        >
          下へ
        </Button>
        <Button
          variant="outlined"
          color="error"
          type="button"
          disabled={disabled}
          aria-label={`質問${index + 1}を削除`}
          onClick={onRemove}
        >
          削除
        </Button>
      </Actions>
    </Panel>
  );
}
