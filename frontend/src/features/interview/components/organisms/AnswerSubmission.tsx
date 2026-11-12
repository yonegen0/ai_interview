/** @file AnswerSubmission.tsx @description 回答作成カード・復元確認・送信状態を構成するOrganism。 */
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlined";
import SyncOutlinedIcon from "@mui/icons-material/SyncOutlined";
import { alpha, styled } from "@mui/material/styles";
import { StarAssistPanel } from "@/features/starAssist/components/organisms/StarAssistPanel";
import { StarAssistTutorial } from "@/features/starAssist/tutorial/StarAssistTutorial";
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
  assistType = "star",
  tutorialContextKey,
  tutorialSessionId,
  tutorialQuestionId,
  exitConfirm = false,
  onChooseOtherQuestion,
  previousAnswer,
  currentAnswer,
  draftStatus,
  onClear,
  onRestorePrevious,
  field,
  count,
  answerKind,
  phase,
  valid,
  inputError,
  error,
  onSubmit,
  onReconfirm,
}: AnswerSubmissionProps) {
  const [confirmCopy, setConfirmCopy] = useState(false);
  // The fixed tutorial never touches the production workspace. A request can only
  // be consumed after MUI has finished closing the tutorial dialog.
  const [tutorialMounted, setTutorialMounted] = useState(false);
  const [tutorialOpen, setTutorialOpen] = useState(false);
  const [nativeDialogOpen, setNativeDialogOpen] = useState(false);
  const [externalOpenRequest, setExternalOpenRequest] = useState<number | null>(null);
  const [unsupportedOpen, setUnsupportedOpen] = useState(false);
  const [launchUnavailable, setLaunchUnavailable] = useState(false);
  const requestSerial = useRef(0);
  const tutorialTriggerRef = useRef<HTMLButtonElement>(null);
  const returnFocusAfterExit = useRef(false);
  const pendingLaunch = useRef<{
    id: number;
    sessionId: string;
    questionId: string;
    contextKey: string;
    assistType: typeof assistType;
  } | null>(null);
  const activeContext = useRef(tutorialContextKey);
  const goToCategoryAfterExit = useRef(false);

  // An unmounted/changed practice or a submitted answer invalidates any pending launch.
  useEffect(() => {
    if (phase === "answering" && activeContext.current === tutorialContextKey) return;
    activeContext.current = tutorialContextKey;
    pendingLaunch.current = null;
    setExternalOpenRequest(null);
    setTutorialOpen(false);
    setUnsupportedOpen(false);
    goToCategoryAfterExit.current = false;
    returnFocusAfterExit.current = false;
  }, [phase, tutorialContextKey]);

  // Wait until the trigger is enabled again after MUI's exit transition.
  useEffect(() => {
    if (tutorialMounted || !returnFocusAfterExit.current) return;
    if (nativeDialogOpen || unsupportedOpen || externalOpenRequest !== null) return;
    returnFocusAfterExit.current = false;
    tutorialTriggerRef.current?.focus();
  }, [tutorialMounted, nativeDialogOpen, unsupportedOpen, externalOpenRequest]);

  const productionAvailable = assistType !== "none" && workspace?.available === true;
  const tutorialEligible = phase === "answering" && answerKind === "initial" &&
    !!tutorialContextKey && !!tutorialSessionId && !!tutorialQuestionId;
  const startTutorial = () => {
    if (!tutorialEligible || tutorialMounted || nativeDialogOpen || unsupportedOpen ||
      externalOpenRequest !== null || confirmCopy || exitConfirm) return;
    pendingLaunch.current = null;
    setLaunchUnavailable(false);
    setTutorialMounted(true);
    setTutorialOpen(true);
  };
  const closeTutorial = () => {
    returnFocusAfterExit.current = true;
    pendingLaunch.current = null;
    setTutorialOpen(false);
  };
  const tryProductionAssist = () => {
    returnFocusAfterExit.current = false;
    if (!tutorialOpen || pendingLaunch.current || !tutorialContextKey ||
      !tutorialSessionId || !tutorialQuestionId) return;
    pendingLaunch.current = {
      id: ++requestSerial.current,
      sessionId: tutorialSessionId,
      questionId: tutorialQuestionId,
      contextKey: tutorialContextKey,
      assistType,
    };
    setTutorialOpen(false);
  };
  const tutorialExited = () => {
    setTutorialMounted(false);
    const request = pendingLaunch.current;
    pendingLaunch.current = null;
    if (!request || request.contextKey !== tutorialContextKey ||
      request.sessionId !== tutorialSessionId || request.questionId !== tutorialQuestionId ||
      request.assistType !== assistType || phase !== "answering" || exitConfirm) return;
    if (request.assistType === "none") {
      setUnsupportedOpen(true);
    } else if (productionAvailable && !nativeDialogOpen && !confirmCopy) {
      setExternalOpenRequest(request.id);
    } else {
      setLaunchUnavailable(true);
    }
  };
  const handleExternalOpenHandled = useCallback((id: number) => {
    setExternalOpenRequest((current) => current === id ? null : current);
  }, []);
  const handleNativeDialogOpenChange = useCallback((open: boolean) => {
    setNativeDialogOpen(open);
  }, []);
  const closeUnsupported = () => {
    goToCategoryAfterExit.current = false;
    setUnsupportedOpen(false);
  };
  const chooseOtherQuestion = () => {
    if (!onChooseOtherQuestion) return;
    goToCategoryAfterExit.current = true;
    setUnsupportedOpen(false);
  };
  const unsupportedExited = () => {
    if (!goToCategoryAfterExit.current) return;
    goToCategoryAfterExit.current = false;
    onChooseOtherQuestion?.();
  };
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
          {phase === "answering" && productionAvailable && workspace && (
            <StarAssistPanel
              workspace={workspace}
              hasAnswer={count > 0}
              tutorialActive={tutorialMounted || unsupportedOpen}
              externalOpenRequest={externalOpenRequest}
              onExternalRequestHandled={handleExternalOpenHandled}
              onDialogOpenChange={handleNativeDialogOpenChange}
            />
          )}
          {tutorialEligible && (
            <div>
              <Button ref={tutorialTriggerRef} type="button" variant="outlined" sx={{ minHeight: 44 }}
                aria-haspopup="dialog" aria-expanded={tutorialOpen}
                disabled={tutorialMounted || nativeDialogOpen || unsupportedOpen ||
                  externalOpenRequest !== null || confirmCopy || exitConfirm}
                onClick={startTutorial}>
                {assistType === "none"
                  ? "回答アシストの使い方を体験"
                  : "使い方を体験する"}
              </Button>
              <Text component="p" variant="caption" color="text.secondary">
                {assistType === "star"
                  ? "入力不要で、回答アシストの使い方を体験できます。"
                  : "エピソード作成アシストを例に、回答アシストの使い方を体験できます。"}
              </Text>
            </div>
          )}
          {launchUnavailable && (
            <Text role="alert" color="error" variant="body2">
              本番アシストを開けませんでした。練習画面からもう一度お試しください。
            </Text>
          )}
          <form onSubmit={onSubmit}>
            <AnswerField
              field={field}
              count={count}
              answerKind={answerKind}
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
      {tutorialMounted && (
        <StarAssistTutorial open={tutorialOpen} onClose={closeTutorial}
          onTryAssist={tryProductionAssist} onExited={tutorialExited} />
      )}
      <Dialog
        open={unsupportedOpen}
        onClose={closeUnsupported}
        onExited={unsupportedExited}
        title="この質問では回答アシストを使用できません"
        content={<Text>この質問では回答アシストを使用できません。ほかの質問からアシスト機能を試せます。</Text>}
        actions={
          <>
            <Button type="button" variant="outlined" onClick={closeUnsupported}>閉じる</Button>
            <Button type="button" variant="contained" onClick={chooseOtherQuestion}>
              別の質問を選ぶ
            </Button>
          </>
        }
      />
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
