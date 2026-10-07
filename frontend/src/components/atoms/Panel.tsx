/** @file Panel.tsx @description コンテンツを区切る共通Surface Atom。 */
"use client";
import { scaledRadius } from "@/theme/tokens";
import { alpha, styled } from "@mui/material/styles";

export const Panel = styled("section")(({ theme }) => ({
  padding: `clamp(${theme.spacing(2.25)}, 4vw, ${theme.spacing(4)})`,
  borderRadius: scaledRadius(theme, 1.5),
  background: alpha(theme.palette.common.white, 0.85),
  border: `1px solid ${alpha(theme.palette.primary.main, 0.14)}`,
  boxShadow: theme.shadows[1],
  marginBottom: theme.spacing(3),
  "p, li": { whiteSpace: "pre-wrap", overflowWrap: "anywhere" },
}));
