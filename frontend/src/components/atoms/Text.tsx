/** @file Text.tsx @description themeの文字スタイルと意味を持つHTML要素を提供する共通Atom。 */
"use client";
import Typography, { type TypographyProps } from "@mui/material/Typography";
import { styled } from "@mui/material/styles";

export type TextProps = TypographyProps;
const StyledText = styled(Typography)({
  overflowWrap: "anywhere",
  whiteSpace: "pre-wrap",
});
export const Text = (props: TextProps) => <StyledText {...props} />;
