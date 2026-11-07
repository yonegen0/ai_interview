/** @file GuideUI.tsx @description 既存テーマに合わせた静的使い方ガイドの共通表示部品。 */
"use client";

import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";

export const GuidePage = styled("div")(({ theme }) => ({
  display: "grid", gap: theme.spacing(3), minWidth: 0,
  maxWidth: 920, margin: "0 auto",
  [theme.breakpoints.down("sm")]: { gap: theme.spacing(2.5) },
}));
export const GuideHeading = styled("h1")(({ theme }) => ({
  ...theme.typography.h1, color: theme.palette.text.primary,
  margin: 0, fontWeight: 800, letterSpacing: "-0.025em",
}));
export const GuideLead = styled("p")(({ theme }) => ({
  ...theme.typography.body1, color: theme.palette.text.secondary,
  margin: 0, lineHeight: 1.8,
}));
export const GuideSurface = styled("section")(({ theme }) => ({
  display: "grid", gap: theme.spacing(2),
  backgroundColor: theme.palette.background.paper,
  padding: theme.spacing(3), minWidth: 0,
  border: "1px solid " + alpha(theme.palette.primary.main, 0.18),
  borderRadius: theme.shape.borderRadius, boxShadow: theme.shadows[2],
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(2) },
}));
export const GuideCards = styled("div")(({ theme }) => ({
  display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: theme.spacing(2),
  [theme.breakpoints.down("sm")]: { gridTemplateColumns: "minmax(0, 1fr)" },
}));
export const GuideAction = styled(Link)(({ theme }) => ({
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  minHeight: 48, minWidth: 0, width: "fit-content",
  maxWidth: "100%", padding: theme.spacing(1.25, 2.5),
  borderRadius: theme.shape.borderRadius,
  textDecoration: "none", backgroundColor: theme.palette.primary.main,
  color: theme.palette.primary.contrastText, fontWeight: 700,
  "&:visited": { color: theme.palette.primary.contrastText },
  "&:hover, &:active": { backgroundColor: theme.palette.primary.dark,
    color: theme.palette.primary.contrastText, textDecoration: "none" },
  "&:focus-visible": { outline: "3px solid " + theme.palette.primary.dark, outlineOffset: 3 },
}));
export const GuideActions = styled("nav")(({ theme }) => ({
  display: "flex", flexWrap: "wrap", alignItems: "center",
  gap: theme.spacing(1.5), minWidth: 0,
  [theme.breakpoints.down("sm")]: {
    "& > a": { flexGrow: 1, textAlign: "center" },
  },
}));
export const GuideEyebrow = styled("span")(({ theme }) => ({
  ...theme.typography.overline, fontWeight: 800, color: theme.palette.primary.dark,
}));
export const GuideSubheading = styled("h2")(({ theme }) => ({
  ...theme.typography.h2, fontWeight: 800, margin: 0, color: theme.palette.text.primary,
}));
export const GuideBack = styled(Link)(({ theme }) => ({
  width: "fit-content", fontSize: theme.typography.body2.fontSize,
}));
