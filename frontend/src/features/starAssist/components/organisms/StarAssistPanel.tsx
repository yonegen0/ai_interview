/** @file StarAssistPanel.tsx @description アシスト入力・成果物・上書き確認を排他的に管理する。 */
"use client";

import { useEffect, useRef, useState } from "react";
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
import { AssistResultDialog } from "./AssistResultDialog";

type View = "closed" | "input" | "result" | "confirm";
type ReturnView = Exclude<View, "confirm">;
type Confirmation = "apply" | "load" | "mine" | "discardStar";
type CandidateId = "A" | "B" | "C";

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
  const [view, setView] = useState<View>("closed");
  const viewRef = useRef<View>("closed");
  const setScreen = (next: View) => {
    viewRef.current = next;
    setView(next);
  };
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const returnView = useRef<ReturnView>("closed");
  const candidateToApply = useRef<CandidateId | null>(null);
  const [requestedGenerationId, setRequestedGenerationId] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const applyLock = useRef(false);
  const meta = assistModes[w.mode];
  const modeMismatch = (w.input.assistType ?? "star") !== w.mode;

  useEffect(() => {
    if (view !== "input" || !requestedGenerationId ||
      w.input.generationId !== requestedGenerationId || w.resultWaiting ||
      w.input.candidates.length !== (w.mode === "star" ? 3 : 1)) return;
    setRequestedGenerationId(null);
    viewRef.current = "result";
    setView("result");
  }, [view, requestedGenerationId, w.input.generationId, w.input.candidates.length, w.resultWaiting, w.mode]);

  const close = () => {
    if (applyLock.current) return;
    setRequestedGenerationId(null);
    setScreen("closed");
  };
  const startConfirmation = (kind: Confirmation, candidateId?: CandidateId) => {
    returnView.current = viewRef.current === "confirm" ? "closed" : viewRef.current;
    candidateToApply.current = candidateId ?? null;
    setConfirm(kind);
    setScreen("confirm");
  };
  const cancelConfirmation = () => {
    setConfirm(null);
    candidateToApply.current = null;
    setScreen(returnView.current);
  };
  const commitApply = async (id: CandidateId) => {
    if (applyLock.current) return;
    applyLock.current = true;
    setApplying(true);
    let applied = false;
    try {
      applied = await w.apply(id);
    } finally {
      applyLock.current = false;
      setApplying(false);
      setRequestedGenerationId(null);
      setScreen(applied ? "closed" : "result");
    }
  };
  const requestApply = (id: CandidateId) => {
    if (!w.input.candidates.some((candidate) => candidate.id === id) || applyLock.current) return;
    if (hasAnswer) startConfirmation("apply", id);
    else void commitApply(id);
  };
  const acceptWaiting = () => {
    if (w.adopt()) {
      setRequestedGenerationId(null);
      setScreen("result");
    }
  };
  const submitConfirmation = async () => {
    const kind = confirm;
    const id = candidateToApply.current;
    if (!kind) return;
    setConfirm(null);
    candidateToApply.current = null;
    if (kind === "apply") {
      if (!id) {
        setScreen("result");
        return;
      }
      // Keep the result visible (with actions disabled) until apply resolves.
      setScreen("result");
      await commitApply(id);
      return;
    }
    setScreen(returnView.current);
    if (kind === "mine") void w.saveMine();
    else if (kind === "discardStar") void w.discardStar();
    else void w.loadSaved();
  };

  return (
    <Area aria-label={"回答の保存と" + meta.label}>
      <Trigger type="button" onClick={() => setScreen("input")}
        aria-haspopup="dialog" aria-expanded={view !== "closed"}>
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
      {modeMismatch && (
        <Alert severity="warning">
          以前のモードの下書きが保存されています。内容を確認してから明示的に破棄してください。
          正式回答欄の下書きは保持されます。
        </Alert>
      )}
      {(modeMismatch || w.pending || w.status === "競合" || w.savedPreview !== null || (w.error && !w.pending)) && (
        <Actions>
          {modeMismatch && (
            <Button type="button" onClick={() => void w.inspectSaved()} disabled={w.loading}>
              旧下書きを確認
            </Button>
          )}
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
              <Button type="button" onClick={() => startConfirmation("load")}>
                保存版を読み込む
              </Button>
              <Button type="button" onClick={() => startConfirmation("mine")}
                disabled={w.pending || w.busy || modeMismatch}>
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
        open={view === "input"}
        onClose={close}
        workspace={w}
        onGenerationQueued={(id) => {
          if (viewRef.current === "input") setRequestedGenerationId(id);
        }}
        onAdopt={acceptWaiting}
        onViewResult={() => {
          setRequestedGenerationId(null);
          setScreen("result");
        }}
        onDiscard={() => startConfirmation("discardStar")}
      />
      <AssistResultDialog
        open={view === "result"}
        onClose={close}
        onBack={() => setScreen("input")}
        onApply={requestApply}
        applying={applying}
        workspace={w}
      />
      <Dialog
        open={view === "confirm" && confirm !== null}
        onClose={cancelConfirmation}
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
            <Button type="button" onClick={cancelConfirmation}>キャンセル</Button>
            <Button type="button" onClick={() => void submitConfirmation()}>
              {confirm === "mine" ? "確認して保存"
                : confirm === "discardStar" ? "破棄する" : "置き換える"}
            </Button>
          </>
        }
      />
    </Area>
  );
}
