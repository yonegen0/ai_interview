/** @file AssistResultPresentation.tsx @description 実成果物と体験版で同じ見た目を利用する表示部品。 */
"use client";

import { Tab, Tabs } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";

export const CandidateTabs = styled(Tabs)(({ theme }) => ({
  minHeight: 0,
  "& .MuiTabs-indicator": { display: "none" },
  "& .MuiTabs-flexContainer": { gap: theme.spacing(1) },
}));
export const CandidateTab = styled(Tab)(({ theme }) => ({
  flex: 1,
  minWidth: 0,
  minHeight: 54,
  padding: theme.spacing(1, 0.5),
  border: `1px solid ${theme.palette.divider}`,
  borderRadius: 12,
  background: alpha(theme.palette.background.paper, 0.82),
  color: theme.palette.text.primary,
  fontWeight: 700,
  textTransform: "none",
  "&.Mui-selected": {
    color: theme.palette.primary.contrastText,
    background: theme.palette.primary.dark,
    borderColor: theme.palette.primary.dark,
    boxShadow: `0 5px 14px ${alpha(theme.palette.primary.main, 0.2)}`,
  },
  "&.Mui-focusVisible": { outline: `3px solid ${theme.palette.primary.main}`, outlineOffset: 2 },
  [theme.breakpoints.down("sm")]: { fontSize: "0.78rem", minHeight: 48 },
}));
export const AnswerCard = styled("section")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1.75),
  padding: theme.spacing(2.5),
  minWidth: 0,
  border: `1px solid ${alpha(theme.palette.primary.main, 0.36)}`,
  borderRadius: 20,
  background: `linear-gradient(145deg, ${alpha(theme.palette.primary.light, 0.12)}, ${alpha(theme.palette.background.paper, 0.93)})`,
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(1.75), borderRadius: 16 },
}));
export const CardHeading = styled("div")(({ theme }) => ({
  display: "flex", alignItems: "center", gap: theme.spacing(1),
  color: theme.palette.primary.dark, fontWeight: 700,
}));
export const AnswerText = styled("p")(({ theme }) => ({
  margin: 0,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
  ...theme.typography.body1,
  lineHeight: 1.9,
  color: theme.palette.text.primary,
}));
export const ActionBar = styled("div")(({ theme }) => ({
  display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.spacing(1),
  "& > :last-child": { marginLeft: "auto" },
  [theme.breakpoints.down("sm")]: {
    "& > :last-child": { marginLeft: 0, width: "100%" },
    "& > :not(:last-child)": { flex: 1 },
  },
}));
