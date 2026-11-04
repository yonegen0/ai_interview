/** @file ChoiceGrid.tsx @description 選択ボタンをレスポンシブに並べる共通Grid。 */
"use client";
import { styled } from "@mui/material/styles";

export const ChoiceGrid = styled("div")(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
  gap: theme.spacing(1.5),
}));
