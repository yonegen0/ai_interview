/** @file Actions.tsx @description 操作要素を折り返して配置する共通レイアウトAtom。 */
"use client";
import { styled } from "@mui/material/styles";

export const Actions = styled("div")(({ theme }) => ({
  display: "flex",
  flexWrap: "wrap",
  gap: theme.spacing(1.5),
  marginTop: theme.spacing(3),
  alignItems: "center",
}));
