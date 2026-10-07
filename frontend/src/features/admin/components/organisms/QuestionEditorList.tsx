/** @file QuestionEditorList.tsx @description Presentation and composition for QuestionEditorList. */
"use client";
import { Text } from "@/components/atoms/Text";
import { QuestionEditorCard } from "../molecules/QuestionEditorCard";
import type { EditorBindings } from "../../model/editor";
export type QuestionEditorListProps = EditorBindings & {
  disabled: boolean;
  onMove: (index: number, direction: -1 | 1) => void;
  onRemove: (index: number) => void;
};
export const QuestionEditorList = ({
  fields,
  control,
  errors,
  disabled,
  onMove,
  onRemove,
}: QuestionEditorListProps) => (
  <>
    {fields.map((field, index) => (
      <QuestionEditorCard
        key={field.fieldKey}
        fieldKey={field.fieldKey}
        index={index}
        control={control}
        errors={errors}
        disabled={disabled}
        first={index === 0}
        last={index === fields.length - 1}
        onMove={(direction) => onMove(index, direction)}
        onRemove={() => onRemove(index)}
      />
    ))}
    {fields.length === 0 && (
      <Text role="alert">質問を1問以上登録してください。</Text>
    )}
  </>
);
