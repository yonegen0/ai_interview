/** @file AnswerSubmission.tsx @description 回答作成カード・復元確認・送信状態を構成するOrganism。 */
"use client";
import { useState } from "react";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlined";
import SyncOutlinedIcon from "@mui/icons-material/SyncOutlined";
import { alpha, styled } from "@mui/material/styles";
import { StarAssistPanel } from "@/features/starAssist/components/organisms/StarAssistPanel";
import { Panel } from "@/components/atoms/Panel";
import { Button } from "@/components/atoms/Button";
import { Text } from "@/components/atoms/Text";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { Dialog } from "@/components/organisms/Dialog";
import { ErrorView } from "@/components/organisms/ErrorView";
import { scaledRadius } from "@/theme/tokens";
import { AnswerField } from "../molecules/AnswerField";
import type { AnswerSubmissionProps } from "../../model/practice";

const ComposerCard = styled(Panel)(({ theme }) => ({
  padding: 0,
  overflow: "hidden",
  borderRadius: scaledRadius(theme, 2),
  boxShadow: theme.shadows[2],
}));
const ComposerHeader = styled("div")(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1.5),
  padding: theme.spacing(2.5, 3),
  backgroundColor: alpha(theme.palette.primary.light, 0.12),
  borderBottom: "1px solid " + alpha(theme.palette.primary.main, 0.08),
  color: theme.palette.primary.dark,
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(2, 2.5) },
}));
const ComposerBody = styled("div")(({ theme }) => ({
  padding: theme.spacing(3),
  display: "grid",
  gap: theme.spacing(2),
  minWidth: 0,
  [theme.breakpoints.down("sm")]: { padding: theme.spacing(2.5, 2) },
}));
const StatusRow = styled("div")(({ theme }) => ({
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  flexWrap: "wrap",
  gap: theme.spacing(1),
  minHeight: theme.spacing(5),
}));
const StatusText = styled("div")(({ theme }) => ({
  display: "inline-flex",
  alignItems: "center",
  gap: theme.spacing(1),
  color: theme.palette.text.secondary,
}));
const SubmitButton = styled(Button)(({ theme }) => ({
  width: "100%",
  minHeight: theme.spacing(7),
  borderRadius: scaledRadius(theme, 2),
  marginTop: theme.spacing(3),
  boxShadow: theme.shadows[2],
}));
const SubmissionCard = styled(MascotCoachCard)(({ theme }) => ({
  marginTop: theme.spacing(2),
}));

export function AnswerSubmission({
  workspace,
  previousAnswer,
  currentAnswer,
  draftStatus,
  onClear,
  onRestorePrevious,
  field,
  count,
  phase,
  valid,
  inputError,
  error,
  onSubmit,
  onReconfirm,
}: AnswerSubmissionProps) {
  const [confirmCopy, setConfirmCopy] = useState(false);
  const canCopyPrevious = previousAnswer !== undefined && !!onRestorePrevious;
  const copyPrevious = () => {
    if (!canCopyPrevious || phase !== "answering" || currentAnswer === previousAnswer) return;
    if ((currentAnswer ?? "").length > 0) {
      setConfirmCopy(true);
      return;
    }
    onRestorePrevious?.();
  };
  const confirmRestore = () => {
    if (phase === "answering" && canCopyPrevious && currentAnswer !== previousAnswer) {
      onRestorePrevious?.();
    }
    setConfirmCopy(false);
  };
  const statusText = phase === "recovery_required"
    ? "送信結果の確認待ち"
    : phase === "submitting"
      ? "回答を送信中"
      : draftStatus === "saved"
        ? "下書き保存済み（この端末）"
        : draftStatus === "unavailable"
          ? "下書きを保存できません（この端末）"
          : "下書きを保存中（この端末）";
  const StatusIcon = phase === "recovery_required" || draftStatus === "unavailable"
    ? ErrorOutlineIcon
    : phase === "answering" && draftStatus === "saved"
      ? CheckCircleOutlineIcon
      : SyncOutlinedIcon;

  return (
    <>
      <ComposerCard aria-label="回答作成">
        <ComposerHeader>
          <EditOutlinedIcon aria-hidden="true" />
          <Text variant="h2" component="h2">回答作成</Text>
        </ComposerHeader>
        <ComposerBody>
          <StatusRow>
            <StatusText role="status" aria-live="polite">
              <StatusIcon fontSize="small" aria-hidden="true" />
              <Text component="span" variant="body2">{statusText}</Text>
            </StatusText>
            {phase === "answering" && onClear && (
              <Button type="button" size="small" color="inherit"
                startIcon={<DeleteOutlineIcon />} onClick={onClear}>
                入力をクリア
              </Button>
            )}
          </StatusRow>
          {phase === "answering" && workspace?.available && (
            <StarAssistPanel workspace={workspace} hasAnswer={count > 0} />
          )}
          <form onSubmit={onSubmit}>
            <AnswerField
              field={field}
              count={count}
              disabled={phase !== "answering"}
              error={inputError}
              canCopyPrevious={canCopyPrevious}
              onCopyPrevious={copyPrevious}
            />
            {phase === "submitting" && (
              <SubmissionCard
                variant="thinking"
                heading={<Text variant="h2" component="h2">回答を送信しています</Text>}
              >
                <Text role="status" aria-live="polite">
                  送信が終わるまで、このままお待ちください。
                </Text>
              </SubmissionCard>
            )}
            {phase === "recovery_required" ? (
              <SubmitButton variant="contained" color="primary" type="button"
                onClick={onReconfirm}>
                送信結果を再確認
              </SubmitButton>
            ) : (
              <SubmitButton variant="contained" color="primary" type="submit"
                disabled={!valid || phase !== "answering"}>
                {phase === "submitting" ? "回答を送信しています…" : "回答を送信"}
              </SubmitButton>
            )}
          </form>
          {error && <ErrorView error={error} />}
        </ComposerBody>
      </ComposerCard>
      <Dialog
        open={confirmCopy}
        onClose={() => setConfirmCopy(false)}
        title="入力中の回答を上書きしますか？"
        content={
          <Text>現在入力している回答を、同じ質問に前回送信した回答で置き換えます。送信やAI生成は開始しません。</Text>
        }
        actions={
          <>
            <Button type="button" variant="outlined" onClick={() => setConfirmCopy(false)}>
              キャンセル
            </Button>
            <Button type="button" variant="contained" onClick={confirmRestore}
              disabled={phase !== "answering"}>
              前回の回答に置き換える
            </Button>
          </>
        }
      />
    </>
  );
}
