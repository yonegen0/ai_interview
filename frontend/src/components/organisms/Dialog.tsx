/**
 * @file Dialog.tsx
 * @description モーダルシェル共通コンポーネント。title / content / actions を props で受け、
 *   本文領域は overflow: visible で Outlined Input のラベル見切れを防ぐ
 */
"use client";

import type { ReactNode } from "react";
import MuiDialog from "@mui/material/Dialog";
import type { DialogProps as MuiDialogProps } from "@mui/material/Dialog";
import MuiDialogActions from "@mui/material/DialogActions";
import MuiDialogContent from "@mui/material/DialogContent";
import MuiDialogTitle from "@mui/material/DialogTitle";
import { styled } from "@mui/material/styles";

/** 共通 Dialog の Props */
export type DialogProps = {
  /** 表示中か（controlled） */
  open: boolean;
  /** 閉じる要求（背景クリック・Escape。実行中ガードは呼び出し側 onClose 内で行う） */
  onClose: () => void;
  /** ダイアログ見出し */
  title: string;
  /** DialogContent 相当の本体 */
  content: ReactNode;
  /** DialogActions 相当のフッター（通常は Button 群） */
  actions: ReactNode;
  /** 最大幅。省略時 sm */
  maxWidth?: MuiDialogProps["maxWidth"];
  /** 幅 100%。省略時 true */
  fullWidth?: boolean;
};

/** Outlined Input の縮小ラベルが DialogContent でクリップされないよう overflow を解除 */
const StyledDialogContent = styled(MuiDialogContent)(({ theme }) => ({
  overflow: "visible",
  ".MuiDialogTitle-root + &": {
    paddingTop: theme.spacing(1),
  },
}));

/**
 * モーダルシェルを表示する
 * @param props 表示に必要なプロパティ
 * @returns ダイアログ UI
 */
export const Dialog = (props: DialogProps) => {
  return (
    <MuiDialog
      open={props.open}
      onClose={props.onClose}
      maxWidth={props.maxWidth ?? "sm"}
      fullWidth={props.fullWidth ?? true}
    >
      <MuiDialogTitle>{props.title}</MuiDialogTitle>
      <StyledDialogContent>{props.content}</StyledDialogContent>
      <MuiDialogActions>{props.actions}</MuiDialogActions>
    </MuiDialog>
  );
};
