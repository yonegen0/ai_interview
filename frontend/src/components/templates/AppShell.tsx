/** @file AppShell.tsx @description 面接練習アプリ共通の画面枠 */
"use client";

import { Suspense, type ReactNode } from "react";
import SpaOutlinedIcon from "@mui/icons-material/SpaOutlined";
import { alpha, styled } from "@mui/material/styles";
import { Link } from "@/components/atoms/Link";
import { Text } from "@/components/atoms/Text";
import { AccountActions } from "@/components/molecules/AccountActions";
import { scaledRadius } from "@/theme/tokens";

const PageContainer = styled("main")(({ theme }) => ({
  width: "min(1040px, calc(100% - 32px))",
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
  margin: theme.spacing(2, 2, 0),
  borderRadius: scaledRadius(theme, 1.25),
  background: theme.palette.background.paper,
  boxShadow: theme.shadows[2],
  border: "1px solid " + alpha(theme.palette.primary.main, 0.09),
  [theme.breakpoints.down("sm")]: { margin: theme.spacing(1, 1, 0) },
}));

const BarInner = styled("div")(({ theme }) => ({
  width: "min(1040px, calc(100% - 32px))",
  minHeight: theme.spacing(9),
  margin: "0 auto",
  padding: theme.spacing(1, 0),
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  flexWrap: "nowrap",
  columnGap: theme.spacing(1),
  rowGap: theme.spacing(0.5),
}));

const Branding = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  minWidth: 0,
  gap: theme.spacing(1.5),
}));

const BrandLink = styled(Link)(({ theme }) => ({
  gap: theme.spacing(1),
  flexShrink: 1,
  minWidth: 0,
  padding: 0,
  fontSize: theme.typography.h3.fontSize,
  fontWeight: 800,
  letterSpacing: "-0.035em",
  whiteSpace: "nowrap",
  [theme.breakpoints.down("sm")]: { fontSize: 15 },
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
export const AppShell = ({ children, headerActions }: { children: ReactNode; headerActions?: ReactNode }) => (
  <Frame>
    <Bar>
      <BarInner>
        <Branding>
          <BrandLink href="/" variant="text">
            <SpaOutlinedIcon aria-hidden="true" fontSize="medium" />
            Interview Pocket
          </BrandLink>
          <Tagline variant="caption" component="span">
            一問ずつ、自信を育てる。
          </Tagline>
        </Branding>
        <Suspense fallback={null}>
          {headerActions ?? <AccountActions />}
        </Suspense>
      </BarInner>
    </Bar>
    <PageContainer>{children}</PageContainer>
  </Frame>
);
