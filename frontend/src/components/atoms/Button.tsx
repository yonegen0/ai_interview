/**
 * @file Button.tsx
 * @description 全画面で利用する共通ボタンコンポーネント
 */
"use client";

import { Button as MuiButton } from "@mui/material";
import type { ButtonProps as MuiButtonProps } from "@mui/material";
import type { Theme } from "@mui/material/styles";
import { alpha, styled } from "@mui/material/styles";

/** 共通ButtonのProps */
export type ButtonProps = MuiButtonProps;

/** styled 用: MUI の color に対応するアクセント色 */
type StyledMuiButtonProps = MuiButtonProps & {
  $buttonColor: NonNullable<MuiButtonProps["color"]>;
};

/** MUI Button の color に対応するアクセント色を返す */
const getAccentColor = (theme: Theme, color: NonNullable<MuiButtonProps["color"]>): string => {
  if (color === "inherit") {
    return theme.palette.text.primary;
  }
  return theme.palette[color].main;
};

/** 共通ボタンUI（$buttonColor で枠・グローの配色を切り替える） */
const StyledMuiButton = styled(MuiButton, {
  shouldForwardProp: (prop) => prop !== "$buttonColor",
})<StyledMuiButtonProps>(({ theme, $buttonColor }) => {
  const accent = getAccentColor(theme, $buttonColor);

  return {
    minWidth: "100px",
    borderRadius: "12px",
    backgroundColor: alpha(theme.palette.background.paper, 0.05),
    backdropFilter: "blur(10px)",
    border: `1px solid ${alpha(theme.palette.background.paper, 0.2)}`,
    color: theme.palette.text.primary,
    padding: "10px 24px",
    boxShadow:
      `0 0 15px ${alpha(accent, 0.3)}, ` + `inset 0 0 10px ${alpha(accent, 0.1)}`,
    transition: theme.transitions.create(["box-shadow", "border-color", "color", "background-color"], {
      duration: theme.transitions.duration.shorter,
    }),
    "&:hover": {
      borderColor: accent,
      boxShadow: `0 0 20px ${alpha(accent, 0.5)}`,
      color: accent,
      backgroundColor: alpha(theme.palette.background.paper, 0.08),
    },
    "&.Mui-disabled": {
      backgroundColor: theme.palette.grey[300],
      borderColor: theme.palette.grey[300],
      color: theme.palette.grey[500],
      boxShadow: "none",
    },
  };
});

/**
 * 共通ボタンコンポーネントを表示する
 * @param props 表示に必要なプロパティ
 * @returns 共通ボタンUI
 */
export const Button = (props: ButtonProps) => {
  const buttonColor = props.color ?? "primary";
  return <StyledMuiButton {...props} $buttonColor={buttonColor} />;
};
