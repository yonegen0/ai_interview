/** @file PracticeCategorySelector.tsx @description カテゴリ練習で使用するカテゴリ選択欄。 */
"use client";

import { styled } from "@mui/material/styles";
import { Select } from "@/components/atoms/Select";
import type { Category } from "@/lib/api/schemas";
import type { PracticeStartView } from "../../model/practiceStart";

const CategoryField = styled("div")(({ theme }) => ({
  marginTop: theme.spacing(2),
  maxWidth: theme.spacing(64),
}));

export type PracticeCategorySelectorProps = {
  categories: NonNullable<PracticeStartView["options"]>["categories"];
  selected: Category | null;
  disabled: boolean;
  onSelect: (category: Category) => void;
};

export const PracticeCategorySelector = ({
  categories,
  selected,
  disabled,
  onSelect,
}: PracticeCategorySelectorProps) => (
  <CategoryField>
    <Select<Category | "">
      label="練習するカテゴリ"
      value={selected ?? ""}
      disabled={disabled || categories.length === 0}
      fullWidth
      options={categories.map(({ id, label, questionCount }) => ({
        value: id,
        label: `${label}（${questionCount}問）`,
      }))}
      onChange={(value) => {
        if (value) onSelect(value);
      }}
    />
  </CategoryField>
);
