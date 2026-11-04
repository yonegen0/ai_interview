/** @file StarAssistPanel.tsx @description 保存状態とSTARダイアログの起動・確認操作。 */
"use client";

import { useState } from "react";
import { Alert } from "@mui/material";
import { styled } from "@mui/material/styles";
import { Button } from "@/components/atoms/Button";
import { Text } from "@/components/atoms/Text";
import { Actions } from "@/components/atoms/Actions";
import { Dialog } from "@/components/organisms/Dialog";
import type { StarWorkspace } from "../../hooks/useStarWorkspace";
import { StarAssistDialog } from "./StarAssistDialog";

const Area = styled("section")(({ theme }) => ({
  marginBlock: theme.spacing(2),
  padding: theme.spacing(2),
  border: "1px solid " + theme.palette.divider,
  borderRadius: theme.shape.borderRadius,
}));

export function StarAssistPanel({
  workspace: w,
  hasAnswer,
}: {
  workspace: StarWorkspace;
  hasAnswer: boolean;
}) {
  const [open, setOpen] = useState(false);
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
    <Area aria-label="回答の保存とSTARアシスト">
      <Text role="status" aria-live="polite">
        下書き：{w.status}{w.loading ? "（保存版を確認中）" : ""}
      </Text>
      {w.error && <Alert severity="error">{w.error}</Alert>}
      {w.migrationWarning && <Alert severity="warning">{w.migrationWarning}</Alert>}
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
        <Button type="button" variant="outlined" onClick={() => setOpen(true)}
          aria-haspopup="dialog" aria-expanded={open}>
          STARアシストを開く
        </Button>
      </Actions>
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
            : confirm === "discardStar" ? "STAR下書きを破棄しますか？"
              : confirm === "mine" ? "自分の内容で保存版を更新しますか？"
                : "保存版を読み込みますか？"
        }
        content={
          <Text>
            {confirm === "mine"
              ? "最新の保存版を確認して、自分の内容を新しい要求で保存します。"
              : confirm === "discardStar"
                ? "STARメモと3案を破棄します。通常回答の入力は保持します。"
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
