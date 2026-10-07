/** @file PracticeModeSelector.tsx @description Presentation and composition for PracticeModeSelector. */
"use client";
import { styled } from "@mui/material/styles";
import { ChoiceButton } from "@/components/atoms/ChoiceButton";
const Grid = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
  gap: theme.spacing(1.5),
}));
export type PracticeModeSelectorProps = {
  mode: "full" | "category";
  total?: number;
  disabled: boolean;
  onSelect: (mode: "full" | "category") => void;
};
export const PracticeModeSelector = ({
  mode,
  total,
  disabled,
  onSelect,
}: PracticeModeSelectorProps) => (
  <Grid>
    <ChoiceButton
      selected={mode === "full"}
      disabled={disabled}
      onClick={() => onSelect("full")}
    >
      全質問を順番に練習{total !== undefined ? `（${total}問）` : ""}
    </ChoiceButton>
    <ChoiceButton
      selected={mode === "category"}
      disabled={disabled}
      onClick={() => onSelect("category")}
    >
      カテゴリ練習
    </ChoiceButton>
  </Grid>
);
