/**
 * @file FullTextDialog.tsx
 * @description 長文をプレーンテキストで全文表示する共通ダイアログ。
 */
"use client";

import type { ReactNode } from "react";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import CloseIcon from "@mui/icons-material/Close";
import IconButton from "@mui/material/IconButton";
import { styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Dialog } from "./Dialog";

export type FullTextDialogProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  text: string;
  icon?: ReactNode;
};

const DialogHeading = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1.5),
  minWidth: 0,
}));

const TitleIcon = styled("span")(({ theme }) => ({
  display: "inline-flex",
  flexShrink: 0,
  alignItems: "center",
  color: theme.palette.primary.main,
}));

const HeadingText = styled("h2")(({ theme }) => ({
  ...theme.typography.h3,
  flex: 1,
  minWidth: 0,
  margin: 0,
  overflowWrap: "anywhere",
}));

const CloseButton = styled(IconButton)(({ theme }) => ({
  flexShrink: 0,
  color: theme.palette.text.secondary,
}));

const FullText = styled("p")(({ theme }) => ({
  ...theme.typography.body1,
  lineHeight: 1.8,
  margin: 0,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
}));

/** 既存のDialog基盤を使い、Esc・フォーカス復帰・本文スクロールを維持する。 */
export function FullTextDialog({
  open,
  onClose,
  title,
  text,
  icon,
}: FullTextDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      scrollContent
      title={
        <DialogHeading>
          <TitleIcon aria-hidden="true">
            {icon ?? <ArticleOutlinedIcon />}
          </TitleIcon>
          <HeadingText>{title}（全文）</HeadingText>
          <CloseButton aria-label="ダイアログを閉じる" onClick={onClose}>
            <CloseIcon />
          </CloseButton>
        </DialogHeading>
      }
      content={<FullText>{text}</FullText>}
      actions={
        <Button variant="text" onClick={onClose}>
          閉じる
        </Button>
      }
    />
  );
}
