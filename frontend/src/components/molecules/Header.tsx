/**
 * @file Header.tsx
 * @description Eyebrow / Title / Description で構成されるパネル共通ヘッダー
 */
"use client";
import { scaledRadius } from "@/theme/tokens";

import { Text } from "@/components/atoms/Text";
import { alpha, styled } from "@mui/material/styles";

/** ヘッダー領域のコンテナ */
const StyledRoot = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(0.75),
}));

/** タイトル上の英字ラベル */
const StyledEyebrow = styled(Text)(({ theme }) => ({
  ...theme.typography.overline,
  textTransform: "uppercase",
  color: theme.palette.primary.dark,
}));

/** タイトル */
const StyledTitle = styled(Text)(({ theme }) => ({
  margin: 0,
  ...theme.typography.h1,
  fontWeight: 700,
  letterSpacing: "-0.01em",
  color: theme.palette.text.primary,
  textShadow: `0 0 24px ${alpha(theme.palette.primary.light, 0.2)}`,
  paddingLeft: theme.spacing(1.5),
  borderLeft: `4px solid ${theme.palette.primary.main}`,
  borderRadius: scaledRadius(theme, 0.125),
  [theme.breakpoints.down("md")]: {
    paddingLeft: theme.spacing(1.25),
    borderLeftWidth: "3px",
  },
}));

/** タイトル下の説明文 */
const StyledDescription = styled(Text)(({ theme }) => ({
  margin: 0,
  ...theme.typography.body2,
  lineHeight: 1.6,
  color: theme.palette.text.secondary,
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
      {props.eyebrow ? (
        <StyledEyebrow variant="overline" component="span">
          {props.eyebrow}
        </StyledEyebrow>
      ) : null}
      <StyledTitle variant="h1" component="h1">
        {props.title}
      </StyledTitle>
      {props.description ? (
        <StyledDescription variant="body2" component="p">
          {props.description}
        </StyledDescription>
      ) : null}
    </StyledRoot>
  );
};
