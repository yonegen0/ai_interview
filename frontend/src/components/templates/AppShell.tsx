/** @file AppShell.tsx @description 面接練習アプリ共通の画面枠 */
"use client";

import { Suspense, type ReactNode } from "react";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import { Text } from "@/components/atoms/Text";
import { AccountActions } from "@/components/molecules/AccountActions";

const PageContainer = styled("main")(({ theme }) => ({
  width: "min(920px, calc(100% - 32px))",
  minWidth: 0,
  margin: "0 auto",
  padding: theme.spacing(4, 0, 9),
  overflowWrap: "anywhere",
  [theme.breakpoints.down("sm")]: {
    paddingTop: theme.spacing(2.5),
    paddingBottom: theme.spacing(6),
  },
}));

const Frame = styled("div")(({ theme }) => ({
  minHeight: "100svh",
  background: `radial-gradient(ellipse at top right, ${alpha(theme.palette.primary.light, 0.14)}, transparent 60%), ${theme.palette.background.default}`,
  "button:focus-visible": {
    outline: `3px solid ${theme.palette.primary.dark}`,
    outlineOffset: 3,
  },
}));

const Bar = styled("header")(({ theme }) => ({
  backgroundColor: alpha(theme.palette.background.paper, 0.78),
  borderBottom: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
}));

const BarInner = styled("div")(({ theme }) => ({
  width: "min(920px, calc(100% - 32px))",
  minHeight: theme.spacing(8),
  margin: "0 auto",
  padding: theme.spacing(1, 0),
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  flexWrap: "wrap",
  columnGap: theme.spacing(2),
  rowGap: theme.spacing(0.5),
}));

const Branding = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  minWidth: 0,
  gap: theme.spacing(2.5),
}));

const BrandLink = styled(Link)(({ theme }) => ({
  flexShrink: 0,
  padding: 0,
  fontSize: theme.typography.body1.fontSize,
  fontWeight: 800,
  letterSpacing: "-0.035em",
  whiteSpace: "nowrap",
  textDecoration: "none",
  "&:hover, &:active": {
    textDecoration: "none",
    opacity: 0.85,
  },
}));

const Tagline = styled(Text)(({ theme }) => ({
  color: theme.palette.text.secondary,
  whiteSpace: "nowrap",
  [theme.breakpoints.down("md")]: {
    display: "none",
  },
}));

/** ブランドと操作を1行優先で配置し、狭い画面では必要な場合だけ折り返す。 */
export const AppShell = ({ children }: { children: ReactNode }) => (
  <Frame>
    <Bar>
      <BarInner>
        <Branding>
          <BrandLink href="/" variant="text">
            Interview Pocket
          </BrandLink>
          <Tagline variant="caption" component="span">
            一問ずつ、自信を育てる。
          </Tagline>
        </Branding>
        <Suspense fallback={null}>
          <AccountActions />
        </Suspense>
      </BarInner>
    </Bar>
    <PageContainer>{children}</PageContainer>
  </Frame>
);
