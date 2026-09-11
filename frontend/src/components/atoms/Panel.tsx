/** @file Panel.tsx @description コンテンツを区切る共通Surface Atom。 */
"use client";
import { alpha, styled } from "@mui/material/styles";

export const Panel = styled("section")(({ theme }) => ({
  padding: "clamp(18px, 4vw, 32px)",
  borderRadius: 24,
  background: alpha(theme.palette.common.white, 0.85),
  border: `1px solid ${alpha(theme.palette.primary.main, 0.14)}`,
  boxShadow: "0 12px 40px #4157390d",
  marginBottom: 24,
  "p, li": { whiteSpace: "pre-wrap", overflowWrap: "anywhere" },
}));
