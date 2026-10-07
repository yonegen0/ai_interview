/** @file Input.tsx @description 状態別の共通装飾とRHF接続を提供する入力Atom。 */
"use client";
import { TextField, type TextFieldProps } from "@mui/material";
import { styled } from "@mui/material/styles";
import { fieldStyles } from "@/theme/fieldStyles";
export type InputProps = TextFieldProps;
const StyledInput = styled(TextField)(({ theme }) => ({
  width: "100%",
  ...fieldStyles(theme),
  "& .MuiInputBase-input": { color: theme.palette.text.primary },
}));
export const Input = (props: InputProps) => <StyledInput {...props} />;
