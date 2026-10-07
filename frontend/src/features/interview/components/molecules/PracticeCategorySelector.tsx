/** @file PracticeCategorySelector.tsx @description Presentation and composition for PracticeCategorySelector. */
"use client";
import { styled } from "@mui/material/styles";
import { ChoiceButton } from "@/components/atoms/ChoiceButton";
import type { Category } from "@/lib/api/schemas";
import type { PracticeStartView } from "../../model/practiceStart";
const Grid = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
  gap: theme.spacing(1.5),
  marginTop: theme.spacing(2),
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
  <Grid>
    {categories.map(({ id, label, questionCount }) => (
      <ChoiceButton
        key={id}
        selected={selected === id}
        disabled={disabled}
        onClick={() => onSelect(id)}
      >
        {label}（{questionCount}問）
      </ChoiceButton>
    ))}
  </Grid>
);
