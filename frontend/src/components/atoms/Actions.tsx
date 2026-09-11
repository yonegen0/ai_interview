/** @file Actions.tsx @description 操作要素を折り返して配置する共通レイアウトAtom。 */
"use client";
import { styled } from "@mui/material/styles";

export const Actions = styled("div")({
  display: "flex",
  flexWrap: "wrap",
  gap: 12,
  marginTop: 24,
  alignItems: "center",
});
