/** @file fieldStyles.ts @description Input・Selectで共有する状態別の入力装飾。 */
import { alpha, type Theme } from "@mui/material/styles";
import { scaledRadius } from "./tokens";

const glow = (color: string) =>
  `0 0 15px ${alpha(color, 0.3)}, inset 0 0 10px ${alpha(color, 0.1)}`;

/** Disabled overrides error; error overrides focus and hover. */
export const fieldStyles = (theme: Theme) => ({
  "& .MuiOutlinedInput-root": {
    borderRadius: scaledRadius(theme, 0.75),
    backgroundColor: alpha(theme.palette.common.white, 0.9),
    backdropFilter: "blur(10px)",
    transition: theme.transitions.create([
      "background-color",
      "box-shadow",
      "border-color",
    ]),
    "& fieldset": { borderColor: theme.palette.grey[300] },
    "&:hover fieldset": { borderColor: theme.palette.grey[400] },
    "&.Mui-focused": {
      backgroundColor: theme.palette.common.white,
      boxShadow: glow(theme.palette.primary.main),
      "& fieldset": {
        borderWidth: "1px",
        borderColor: theme.palette.primary.main,
      },
    },
    "&.Mui-error, &.Mui-error:hover, &.Mui-error.Mui-focused": {
      "& fieldset": { borderColor: theme.palette.error.main },
    },
    "&.Mui-error.Mui-focused": { boxShadow: glow(theme.palette.error.main) },
    "&.Mui-disabled, &.Mui-disabled:hover, &.Mui-disabled.Mui-focused": {
      boxShadow: "none",
      "& fieldset": { borderColor: theme.palette.action.disabled },
    },
    "&.Mui-disabled.Mui-error, &.Mui-disabled.Mui-error:hover, &.Mui-disabled.Mui-error.Mui-focused":
      {
        boxShadow: "none",
        "& fieldset": { borderColor: theme.palette.action.disabled },
      },
  },
  "& .MuiInputLabel-root": {
    fontWeight: 600,
    color: theme.palette.text.secondary,
    "&.Mui-focused": {
      color: theme.palette.primary.main,
      textShadow: `0 0 5px ${theme.palette.primary.main}`,
    },
    "&.Mui-error, &.Mui-error.Mui-focused": {
      color: theme.palette.error.main,
      textShadow: "none",
    },
    "&.Mui-disabled, &.Mui-disabled.Mui-focused, &.Mui-disabled.Mui-error, &.Mui-disabled.Mui-error.Mui-focused":
      {
        color: theme.palette.text.disabled,
        textShadow: "none",
      },
  },
  "& .MuiFormHelperText-root": { marginTop: theme.spacing(1), lineHeight: 1.4 },
});
