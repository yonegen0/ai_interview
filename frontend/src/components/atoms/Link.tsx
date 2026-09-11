/**
 * @file Link.tsx
 * @description 画面遷移に利用する共通リンクコンポーネント
 */
"use client";

import type { ComponentPropsWithRef } from "react";
import NextLink from "next/link";
import { alpha, styled } from "@mui/material/styles";

/** 共通Linkの表示形式 */
type LinkVariant = "underline" | "text";

/** 共通LinkのProps */
export type LinkProps = ComponentPropsWithRef<typeof NextLink> & {
  variant?: LinkVariant;
};

/** styled用の内部Props */
type LinkBaseProps = Omit<ComponentPropsWithRef<typeof NextLink>, "as"> & {
  nextAs?: ComponentPropsWithRef<typeof NextLink>["as"];
};

/** MUI styledのasとNext.js Linkのasが衝突しないよう内部名へ変換する */
const LinkBase = ({ nextAs, ...props }: LinkBaseProps) => (
  <NextLink {...props} as={nextAs} />
);

/** 表示形式に応じた共通リンクUI */
const StyledLink = styled(LinkBase, {
  shouldForwardProp: (prop) => prop !== "$variant",
})<{ $variant: LinkVariant }>(({ theme, $variant }) => ({
  boxSizing: "border-box",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "flex-start",
  minWidth: 0,
  minHeight: 44,
  maxWidth: "100%",
  padding: "8px 4px",
  border: 0,
  borderRadius: 4,
  backgroundColor: "transparent",
  color: theme.palette.primary.dark,
  fontFamily: theme.typography.fontFamily,
  fontSize: theme.typography.body1.fontSize,
  fontWeight: $variant === "text" ? 800 : 600,
  lineHeight: theme.typography.body1.lineHeight,
  letterSpacing: "normal",
  textAlign: "left",
  textDecorationLine: $variant === "underline" ? "underline" : "none",
  textDecorationColor: alpha(theme.palette.primary.dark, 0.55),
  textDecorationThickness: "1px",
  textUnderlineOffset: "4px",
  textDecorationSkipInk: "auto",
  whiteSpace: "normal",
  overflowWrap: "anywhere",
  transition: theme.transitions.create("text-decoration-color", {
    duration: theme.transitions.duration.shorter,
  }),
  "&:visited": {
    color: theme.palette.primary.dark,
  },
  "&:hover, &:active": {
    color: theme.palette.primary.dark,
    textDecorationLine: "underline",
    textDecorationColor: theme.palette.primary.dark,
    textDecorationThickness: "2px",
  },
  "&:focus-visible": {
    outline: `3px solid ${theme.palette.primary.dark}`,
    outlineOffset: 3,
    textDecorationLine: "underline",
    textDecorationColor: theme.palette.primary.dark,
    textDecorationThickness: "2px",
  },
  "@media (prefers-reduced-motion: reduce)": {
    transition: "none",
  },
}));

/**
 * Next.jsの画面遷移を共通デザインで表示する
 * @param props 遷移先と表示に必要なプロパティ
 * @returns 共通リンクUI
 */
export const Link = ({
  variant = "underline",
  as: nextAs,
  ...props
}: LinkProps) => <StyledLink {...props} nextAs={nextAs} $variant={variant} />;
