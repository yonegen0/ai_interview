/** @file AppShell.tsx @description 面接練習アプリ共通の画面枠 */
"use client";
import type { ReactNode } from "react";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
const PageContainer = styled("main")(({ theme }) => ({
  width: "min(920px, calc(100% - 32px))",
  margin: "0 auto",
  padding: "40px 0 72px",
  overflowWrap: "anywhere",
  [theme.breakpoints.down("sm")]: { paddingTop: 24 },
}));
const Frame = styled("div")(({ theme }) => ({
  minHeight: "100svh",
  background: `radial-gradient(ellipse at top right, #dce5d6, transparent 65%), ${theme.palette.background.default}`,
  "button:focus-visible": {
    outline: `3px solid ${theme.palette.primary.dark}`,
    outlineOffset: 3,
  },
}));
const Bar = styled("header")(({ theme }) => ({
  padding: "18px 24px",
  borderBottom: `1px solid ${alpha(theme.palette.primary.main, 0.15)}`,
  display: "flex",
  justifyContent: "space-between",
  flexWrap: "wrap",
  gap: 12,
}));
/** 共通ブランドとコンテンツ幅を提供する */
export const AppShell = ({ children }: { children: ReactNode }) => (
  <Frame>
    <Bar>
      <Link href="/" variant="text">
        Interview Pocket
      </Link>
      <span>一問ずつ、自信を育てる。</span>
    </Bar>
    <PageContainer>{children}</PageContainer>
  </Frame>
);
