/** @file Button.tsx @description 主要・補助・危険操作を区別する共通Button。 */
"use client";
import {
  Button as MuiButton,
  type ButtonProps as MuiButtonProps,
} from "@mui/material";
import { alpha, darken, styled } from "@mui/material/styles";
import { scaledRadius } from "@/theme/tokens";
export type ButtonProps = MuiButtonProps;
const StyledButton = styled(MuiButton, {
  shouldForwardProp: (prop) => prop !== "$buttonColor" && prop !== "$variant",
})<{
  $buttonColor: NonNullable<ButtonProps["color"]>;
  $variant: NonNullable<ButtonProps["variant"]>;
}>(({ theme, $buttonColor, $variant }) => {
  const accent =
    $buttonColor === "inherit"
      ? theme.palette.text.primary
      : theme.palette[$buttonColor].main;
  const contrast =
    $buttonColor === "inherit"
      ? theme.palette.background.paper
      : theme.palette[$buttonColor].contrastText;
  const contained = $variant === "contained";
  const outlined = $variant === "outlined";
  return {
    minWidth: theme.spacing(12.5),
    minHeight: theme.spacing(5.5),
    borderRadius: scaledRadius(theme, 0.75),
    padding: theme.spacing(1.25, 3),
    color: contained ? contrast : accent,
    border: outlined
      ? `1px solid ${alpha(accent, 0.65)}`
      : "1px solid transparent",
    backgroundColor: contained
      ? accent
      : outlined
        ? alpha(theme.palette.background.paper, 0.85)
        : "transparent",
    backdropFilter: outlined ? "blur(10px)" : "none",
    boxShadow: contained ? `0 3px 12px ${alpha(accent, 0.2)}` : "none",
    transition: theme.transitions.create([
      "box-shadow",
      "border-color",
      "background-color",
    ]),
    "&:hover": {
      color: contained ? contrast : accent,
      backgroundColor: contained ? darken(accent, 0.1) : alpha(accent, 0.08),
      borderColor: outlined ? accent : "transparent",
      boxShadow: contained ? `0 4px 16px ${alpha(accent, 0.3)}` : "none",
    },
    "&:focus-visible, &.Mui-focusVisible": {
      outline: `3px solid ${accent}`,
      outlineOffset: 3,
    },
    "&.Mui-disabled": {
      backgroundColor: contained ? theme.palette.grey[300] : "transparent",
      borderColor: outlined ? theme.palette.action.disabled : "transparent",
      color: theme.palette.text.disabled,
      boxShadow: "none",
    },
    "@media (prefers-reduced-motion: reduce)": { transition: "none" },
  };
});
export const Button = (props: ButtonProps) => (
  <StyledButton
    {...props}
    $buttonColor={props.color ?? "primary"}
    $variant={props.variant ?? "text"}
  />
);
