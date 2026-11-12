/**
 * @file Dialog.tsx
 * @description 共通モーダル。既存の表示挙動を維持しつつ、長い内容とモバイル全画面にも対応。
 */
"use client";

import type { ReactNode } from "react";
import MuiDialog from "@mui/material/Dialog";
import type { DialogProps as MuiDialogProps } from "@mui/material/Dialog";
import MuiDialogActions from "@mui/material/DialogActions";
import MuiDialogContent from "@mui/material/DialogContent";
import MuiDialogTitle from "@mui/material/DialogTitle";
import { styled } from "@mui/material/styles";

export type DialogProps = {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  content: ReactNode;
  actions: ReactNode;
  maxWidth?: MuiDialogProps["maxWidth"];
  fullWidth?: boolean;
  /** モバイル等で画面全体を使う場合のみ指定する。 */
  fullScreen?: boolean;
  /** 長いフォームの時のみスクロール可能な本文を利用する。 */
  scrollContent?: boolean;
  /** Called after the existing close transition finishes. */
  onExited?: () => void;
};

const StyledDialogContent = styled(MuiDialogContent, {
  shouldForwardProp: (prop) => prop !== "$scrollContent",
})<{ $scrollContent: boolean }>(({ theme, $scrollContent }) => ({
  overflow: $scrollContent ? "auto" : "visible",
  minHeight: 0,
  ".MuiDialogTitle-root + &": { paddingTop: theme.spacing(1) },
}));

export const Dialog = (props: DialogProps) => (
  <MuiDialog
    open={props.open}
    onClose={props.onClose}
    maxWidth={props.maxWidth ?? "sm"}
    fullWidth={props.fullWidth ?? true}
    fullScreen={props.fullScreen ?? false}
    slotProps={{ transition: { onExited: props.onExited } }}
  >
    <MuiDialogTitle component={typeof props.title === "string" ? "h2" : "div"}>
      {props.title}
    </MuiDialogTitle>
    <StyledDialogContent $scrollContent={props.scrollContent ?? false}>
      {props.content}
    </StyledDialogContent>
    <MuiDialogActions>{props.actions}</MuiDialogActions>
  </MuiDialog>
);
