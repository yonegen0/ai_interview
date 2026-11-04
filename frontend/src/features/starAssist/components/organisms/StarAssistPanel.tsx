/** @file StarAssistPanel.tsx @description STAR起動カードと保存・競合復旧操作をまとめる。 */
"use client";

import { useState } from "react";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { Alert } from "@mui/material";
import { alpha, styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Text } from "@/components/atoms/Text";
import { Actions } from "@/components/atoms/Actions";
import { Dialog } from "@/components/organisms/Dialog";
import type { StarWorkspace } from "../../hooks/useStarWorkspace";
import { assistModes } from "../../model/steps";
import { StarAssistDialog } from "./StarAssistDialog";

const Area = styled("section")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(1.5),
}));
const Trigger = styled(Button)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing(1.5),
  width: "100%",
  padding: theme.spacing(2, 2.5),
  minHeight: theme.spacing(10),
  textAlign: "left",
  borderRadius: theme.shape.borderRadius,
  border: "1px solid " + alpha(theme.palette.primary.main, 0.1),
  backgroundColor: alpha(theme.palette.primary.light, 0.11),
  color: theme.palette.text.primary,
  "&:hover": { backgroundColor: alpha(theme.palette.primary.light, 0.2) },
  "&:focus-visible": {
    outline: "3px solid " + theme.palette.primary.main,
    outlineOffset: 2,
  },
}));
const Icon = styled(AutoAwesomeOutlinedIcon)(({ theme }) => ({
  flexShrink: 0,
  color: theme.palette.primary.main,
  fontSize: theme.spacing(4.5),
}));
const TriggerCopy = styled("span")(({ theme }) => ({
  display: "grid",
  flex: 1,
  minWidth: 0,
  gap: theme.spacing(0.25),
}));
const TriggerTitle = styled("span")(({ theme }) => ({
  ...theme.typography.h3,
  color: theme.palette.text.primary,
  fontWeight: 700,
}));
const TriggerCaption = styled("span")(({ theme }) => ({
  ...theme.typography.body2,
  color: theme.palette.text.secondary,
  whiteSpace: "normal",
}));
const Status = styled("div")(({ theme }) => ({
  color: theme.palette.text.secondary,
  paddingInline: theme.spacing(0.5),
}));

export function StarAssistPanel({
  workspace: w,
  hasAnswer,
}: {
  workspace: StarWorkspace;
  hasAnswer: boolean;
}) {
  const [open, setOpen] = useState(false);
  const meta = assistModes[w.mode];
  const [confirm, setConfirm] = useState<
    "apply" | "load" | "mine" | "discardStar" | null
  >(null);

  const apply = () => {
    if (hasAnswer) setConfirm("apply");
    else {
      setOpen(false);
      void w.apply();
    }
  };

  return (
    <Area aria-label={"回答の保存と" + meta.label}>
      <Trigger type="button" onClick={() => setOpen(true)}
        aria-haspopup="dialog" aria-expanded={open}>
        <Icon aria-hidden="true" />
        <TriggerCopy>
          <TriggerTitle>{meta.label}</TriggerTitle>
          <TriggerCaption>{meta.description}</TriggerCaption>
        </TriggerCopy>
        <ChevronRightIcon color="primary" aria-hidden="true" />
      </Trigger>
      <Status role="status" aria-live="polite">
        <Text component="span" variant="caption">
          {meta.label}下書き：{w.status}{w.loading ? "（保存版を確認中）" : ""}
        </Text>
      </Status>
      {w.error && <Alert severity="error">{w.error}</Alert>}
      {w.migrationWarning && <Alert severity="warning">{w.migrationWarning}</Alert>}
      {(w.pending || w.status === "競合" || w.savedPreview !== null || (w.error && !w.pending)) && (
        <Actions>
          {w.pending && (
            <Button type="button" onClick={() => void w.recover()} disabled={w.busy}>
              保存結果を再確認
            </Button>
          )}
          {w.status === "競合" && (
            <>
              <Button type="button" onClick={() => void w.inspectSaved()}>
                保存版を確認
              </Button>
              <Button type="button" onClick={() => setConfirm("load")}>
                保存版を読み込む
              </Button>
              <Button type="button" onClick={() => setConfirm("mine")}
                disabled={w.pending || w.busy}>
                自分の内容を保存
              </Button>
            </>
          )}
          {w.savedPreview !== null && <Text>現在の保存版：{w.savedPreview}</Text>}
          {w.error && !w.pending && (
            <Button type="button" onClick={w.refresh}>補助保存を再読込み</Button>
          )}
        </Actions>
      )}
      <StarAssistDialog
        open={open}
        onClose={() => setOpen(false)}
        workspace={w}
        onApply={apply}
        onDiscard={() => setConfirm("discardStar")}
      />
      <Dialog
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        title={
          confirm === "apply" ? "入力中の回答を置き換えますか？"
            : confirm === "discardStar" ? meta.label + "の下書きを破棄しますか？"
              : confirm === "mine" ? "自分の内容で保存版を更新しますか？"
                : "保存版を読み込みますか？"
        }
        content={
          <Text>
            {confirm === "mine"
              ? "最新の保存版を確認して、自分の内容を新しい要求で保存します。"
              : confirm === "discardStar"
                ? "回答アシストのメモと候補を破棄します。通常回答の入力は保持します。"
                : "入力中の内容を置き換えます。"}
            正式送信・評価は開始しません。
          </Text>
        }
        actions={
          <>
            <Button type="button" onClick={() => setConfirm(null)}>
              キャンセル
            </Button>
            <Button type="button" onClick={() => {
              if (confirm === "apply") {
                setOpen(false);
                void w.apply();
              }
              else if (confirm === "mine") void w.saveMine();
              else if (confirm === "discardStar") void w.discardStar();
              else void w.loadSaved();
              setConfirm(null);
            }}>
              {confirm === "mine" ? "確認して保存"
                : confirm === "discardStar" ? "破棄する" : "置き換える"}
            </Button>
          </>
        }
      />
    </Area>
  );
}
