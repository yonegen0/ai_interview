/** @file Muted.tsx @description 補助情報を控えめに表示する共通テキストAtom。 */
"use client";
import { styled } from "@mui/material/styles";

export const Muted = styled("p")(({ theme }) => ({
  color: theme.palette.text.secondary,
  lineHeight: 1.8,
}));
