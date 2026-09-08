/**
 * @file Header.tsx
 * @description Eyebrow / Title / Description で構成されるパネル共通ヘッダー
 */
"use client";

import { alpha, styled } from "@mui/material/styles";

/** ヘッダー領域のコンテナ */
const StyledRoot = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(0.75),
}));

/** タイトル上の英字ラベル */
const StyledEyebrow = styled("span")(({ theme }) => ({
  fontSize: "11px",
  fontWeight: 700,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: theme.palette.primary.dark,
}));

/** タイトル */
const StyledTitle = styled("h1")(({ theme }) => ({
  margin: 0,
  fontSize: "28px",
  fontWeight: 700,
  letterSpacing: "-0.01em",
  color: theme.palette.text.primary,
  textShadow: `0 0 24px ${alpha(theme.palette.primary.light, 0.2)}`,
  paddingLeft: "12px",
  borderLeft: `4px solid ${theme.palette.primary.main}`,
  borderRadius: "2px",
  [theme.breakpoints.down("md")]: {
    fontSize: "22px",
    paddingLeft: "10px",
    borderLeftWidth: "3px",
  },
}));

/** タイトル下の説明文 */
const StyledDescription = styled("p")(({ theme }) => ({
  margin: 0,
  fontSize: "14px",
  lineHeight: 1.6,
  color: theme.palette.text.secondary,
  [theme.breakpoints.down("md")]: {
    fontSize: "13px",
  },
}));

/** Header の Props */
type HeaderProps = {
  /** タイトル上の英字ラベル（省略可） */
  eyebrow?: string;
  /** タイトル本文 */
  title: string;
  /** タイトル下の説明文（省略可） */
  description?: string;
};

/**
 * パネル共通のヘッダー領域を表示する
 * @param props 表示に必要なプロパティ
 * @returns ヘッダーUI
 */
export const Header = (props: HeaderProps) => {
  return (
    <StyledRoot>
      {props.eyebrow ? <StyledEyebrow>{props.eyebrow}</StyledEyebrow> : null}
      <StyledTitle>{props.title}</StyledTitle>
      {props.description ? (
        <StyledDescription>{props.description}</StyledDescription>
      ) : null}
    </StyledRoot>
  );
};
