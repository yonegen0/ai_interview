/** @file PracticeQuick.tsx @description Single-question quick start with fail-closed recovery. */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import EmojiEventsRoundedIcon from "@mui/icons-material/EmojiEventsRounded";
import { Box, Typography } from "@mui/material";
import { useRouter } from "next/navigation";
import { Panel } from "@/components/atoms/Panel";
import { Button } from "@/components/atoms/Button";
import { Link } from "@/components/atoms/Link";
import { Text } from "@/components/atoms/Text";
import { Header } from "@/components/molecules/Header";
import { ErrorView } from "@/components/organisms/ErrorView";
import { useOperationScope } from "@/hooks/useOperationScope";
import { getPracticeProgress, getPracticeResume } from "@/lib/api/practiceProgress";
import { createSession, getQuestion } from "@/lib/api/interview";
import { ApiError, uncertain } from "@/lib/api/client";
import { createSchema, idSchema } from "@/lib/api/schemas";
import { scopedKey, answerRecoverySchema, operationSchema } from "@/lib/storage/recovery";

type View =
  | { status: "loading" }
  | { status: "complete"; completed: number; total: number }
  | { status: "empty" }
  | { status: "changed" }
  | { status: "error"; error: Error };

const CREATE_KEY = "pocket:create:quick";

type LocalResume = { id: string; pending: boolean };

/** Search only this authenticated tab's existing answer recovery keys. */
function localResumeCandidate(scope: string | null, questionId: string): LocalResume | null {
  const prefix = scopedKey("pocket:answer:", scope);
  if (!prefix) return null;
  const candidates: LocalResume[] = [];
  // If storage cannot be enumerated, absence is unknown: never create a session.
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i);
    if (!key?.startsWith(prefix)) continue;
    const id = key.slice(prefix.length);
    if (!idSchema.safeParse(id).success) continue;
    const raw = sessionStorage.getItem(key);
    if (!raw) continue;
    let parsed: ReturnType<typeof answerRecoverySchema.safeParse>;
    try {
      parsed = answerRecoverySchema.safeParse(JSON.parse(raw));
    } catch {
      continue;
    }
    if (!parsed.success || parsed.data.questionId !== questionId) continue;
    if (!parsed.data.pending && !parsed.data.draft.trim() && !(
      parsed.data.version === 3 && parsed.data.serverDraftId
    )) continue;
    candidates.push({ id, pending: !!parsed.data.pending });
  }
  // An unresolved submission in this tab takes precedence over a plain draft.
  return candidates.find((candidate) => candidate.pending) ?? candidates.at(-1) ?? null;
}

export function PracticeQuick() {
  const router = useRouter();
  const { scope, isActive, storage } = useOperationScope();
  const [view, setView] = useState<View>({ status: "loading" });
  const locked = useRef(false);
  const navigate = useCallback((sessionId: string) => {
    if (isActive()) router.replace(`/practice/session/?sessionId=${sessionId}`);
  }, [router, isActive]);

  const start = useCallback(async () => {
    if (!isActive() || locked.current) return;
    locked.current = true;
    setView({ status: "loading" });
    try {
      // A lost POST response must be resolved with its original body and key.
      const operation = storage.readSaved(CREATE_KEY, operationSchema);
      if (operation) {
        if (!operation.body || operation.body.mode !== "quick") {
          throw new ApiError("INVALID_RESPONSE", 0);
        }
        const resumed = await createSession(operation.body, operation.key);
        if (!isActive()) return;
        storage.removeSaved(CREATE_KEY);
        navigate(resumed.sessionId);
        return;
      }

      // Do not use the home card's cached progress; always fetch again.
      const progress = await getPracticeProgress();
      if (!isActive()) return;
      if (progress.totalQuestions === 0) {
        setView({ status: "empty" });
        return;
      }
      if (progress.nextIncompleteQuestionId === null) {
        setView({
          status: "complete",
          completed: progress.completedQuestions,
          total: progress.totalQuestions,
        });
        return;
      }
      const questionId = progress.nextIncompleteQuestionId;
      const local = localResumeCandidate(scope, questionId);
      const candidate = await getPracticeResume(questionId, local?.id, local?.pending);
      if (!isActive()) return;
      if (candidate.status === "changed") {
        setView({ status: "changed" });
        return;
      }
      if (candidate.status === "resume") {
        // Verify the session's current question and local recovery context before navigation.
        const session = await getQuestion(candidate.sessionId);
        if (!isActive()) return;
        if (session.question.id !== questionId) {
          throw new ApiError("SESSION_STATE_CONFLICT", 409);
        }
        if (candidate.reason === "local" && (
          candidate.questionNumber !== session.questionNumber ||
          !local || local.id !== session.sessionId
        )) {
          throw new ApiError("SESSION_STATE_CONFLICT", 409);
        }
        navigate(candidate.sessionId);
        return;
      }

      // Only a confirmed 'none' permits a new session and monthly quota increment.
      const body = createSchema.parse({
        mode: "quick",
        questionId,
        bankVersion: progress.bankVersion,
        difficulty: "standard",
      });
      const next = { version: 1 as const, key: crypto.randomUUID(), body };
      if (!storage.save(CREATE_KEY, next)) {
        throw new ApiError("INVALID_RESPONSE", 0);
      }
      try {
        const created = await createSession(body, next.key);
        if (!isActive()) return;
        storage.removeSaved(CREATE_KEY);
        navigate(created.sessionId);
      } catch (error) {
        if (!uncertain(error)) storage.removeSaved(CREATE_KEY);
        throw error;
      }
    } catch (error) {
      if (isActive()) setView({
        status: "error",
        error: error instanceof Error ? error : new Error("練習を開始できませんでした。"),
      });
    } finally {
      locked.current = false;
    }
  }, [isActive, storage, scope, navigate]);

  useEffect(() => { void start(); }, [start]);

  return (
    <Box sx={{ display: "grid", gap: 3, maxWidth: 760 }}>
      {view.status === "complete" ? (
        <Panel>
          <Box sx={{ textAlign: "center", py: 3, display: "grid", justifyItems: "center", gap: 2 }}>
            <EmojiEventsRoundedIcon color="primary" sx={{ fontSize: 64 }} aria-hidden="true" />
            <Typography component="h1" variant="h4" sx={{ fontWeight: 800, color: "primary.dark" }}>
              全{view.total}問達成！おめでとうございます
            </Typography>
            <Typography variant="h5">{view.completed} / {view.total} 問完了</Typography>
            <Typography>すべての質問を練習しました。繰り返し練習して、さらに自信をつけていきましょう。</Typography>
            <Link href="/practice/category/">カテゴリから復習する</Link>
            <Link href="/">ホームへ戻る</Link>
          </Box>
        </Panel>
      ) : view.status === "empty" ? (
        <Panel>
          <Header title="練習できる質問がありません" description="現在、練習可能な質問が登録されていません。" />
          <Link href="/">ホームへ戻る</Link>
        </Panel>
      ) : view.status === "changed" ? (
        <Panel>
          <Header title="質問が更新されました" description="以前の下書きは保持されています。現在の質問内容を確認してから練習してください。" />
          <Link href="/practice/category/">カテゴリから練習する</Link>
          <Link href="/">ホームへ戻る</Link>
        </Panel>
      ) : view.status === "error" ? (
        <Panel>
          <Header title="練習を確認できませんでした" description="下書き・開始操作は保持されています。通信と認証を確認して再試行してください。" />
          <ErrorView error={view.error} />
          <Button variant="contained" onClick={() => void start()}>同じ操作で再確認する</Button>
          <Link href="/">ホームへ戻る</Link>
        </Panel>
      ) : (
        <Panel>
          <Header title="練習を準備しています" description="未完了の質問と保存済みの回答を確認しています。" />
          <Text role="status">練習の開始状態を確認しています…</Text>
        </Panel>
      )}
    </Box>
  );
}
