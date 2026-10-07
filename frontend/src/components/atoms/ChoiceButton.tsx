/** @file ChoiceButton.tsx @description 選択状態を表示する共通Button。 */
"use client";
import { alpha, styled } from "@mui/material/styles";
import { Button, type ButtonProps } from "./Button";
export type ChoiceButtonProps = ButtonProps & { selected?: boolean };
const Choice = styled(Button)(({ theme }) => ({
  justifyContent: "flex-start",
  textAlign: "left",
  width: "100%",
  padding: theme.spacing(2.25),
  minHeight: theme.spacing(8.75),
  border: `2px solid ${alpha(theme.palette.primary.main, 0.35)}`,
  borderRadius: theme.shape.borderRadius,
  background: theme.palette.background.paper,
  color: theme.palette.text.primary,
  "&[aria-pressed=true]": {
    background: alpha(theme.palette.primary.light, 0.2),
    borderColor: theme.palette.primary.dark,
  },
  "&:focus-visible": {
    outline: `3px solid ${theme.palette.primary.dark}`,
    outlineOffset: 3,
  },
}));
export const ChoiceButton = ({
  selected = false,
  ...props
}: ChoiceButtonProps) => (
  <Choice type="button" variant="outlined" {...props} aria-pressed={selected} />
);
