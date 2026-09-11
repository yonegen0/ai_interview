/** @file FeedbackResult.tsx @description 結果取得と再挑戦・冪等な次問操作 */
"use client";
import { useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { idSchema, type Feedback, type Session } from "@/lib/api/schemas";
import { getFeedback } from "@/lib/api/feedback";
import { getQuestion, nextQuestion } from "@/lib/api/interview";
import { uncertain } from "@/lib/api/client";
import {
  operationSchema,
  readSaved,
  save,
  removeSaved,
} from "@/lib/storage/recovery";
import { ErrorView } from "@/components/organisms/ErrorView";
import { Actions } from "@/components/atoms/Actions";
import { Button } from "@/components/atoms/Button";
import { Link } from "@/components/atoms/Link";
import { FeedbackCard } from "@/features/feedback/components/organisms/FeedbackCard";
export const FeedbackResult = () => {
  const params = useSearchParams();
  const id = params.get("attemptId") ?? "";
  const query = useQuery({
    queryKey: ["feedback", id],
    queryFn: ({ signal }) => getFeedback(id, signal),
    enabled: idSchema.safeParse(id).success,
  });
  if (!idSchema.safeParse(id).success)
    return <ErrorView error={new Error("回答IDを確認してください。")} />;
  if (query.isPending) return <p role="status">結果を読み込んでいます…</p>;
  if (query.error)
    return <ErrorView error={query.error} retry={() => void query.refetch()} />;
  return <ResultActions key={id} feedback={query.data} />;
};
const ResultActions = ({ feedback }: { feedback: Feedback }) => {
  const router = useRouter();
  const client = useQueryClient();
  const locked = useRef(false);
  const key = `pocket:next:${feedback.attemptId}`;
  const [initial] = useState(() => readSaved(key, operationSchema));
  const pending = useRef(initial);
  const [recovering, setRecovering] = useState(!!initial);
  const session = useQuery({
    queryKey: ["session", feedback.sessionId],
    queryFn: ({ signal }) => getQuestion(feedback.sessionId, signal),
  });
  const mutation = useMutation({
    mutationFn: (requestKey: string) =>
      nextQuestion(feedback.sessionId, feedback.attemptId, requestKey),
  });
  const current = (value?: Session) =>
    value?.questionNumber === feedback.questionNumber &&
    value.activeAttempt?.attemptId === feedback.attemptId &&
    value.activeAttempt.status === "completed";
  const canRetry = current(session.data) && !recovering && !mutation.isPending;
  const next = async () => {
    if (locked.current) return;
    locked.current = true;
    const operation = pending.current ?? {
      version: 1 as const,
      key: crypto.randomUUID(),
      fromAttemptId: feedback.attemptId,
    };
    pending.current = operation;
    save(key, operation);
    try {
      const value = await mutation.mutateAsync(operation.key);
      removeSaved(key);
      client.setQueryData(["session", feedback.sessionId], value);
      router.push(`/practice/session/?sessionId=${feedback.sessionId}`);
    } catch (error) {
      if (uncertain(error)) setRecovering(true);
      else {
        pending.current = null;
        setRecovering(false);
        removeSaved(key);
        void session.refetch();
      }
    } finally {
      locked.current = false;
    }
  };
  return (
    <>
      <FeedbackCard feedback={feedback} />
      {session.isPending ? (
        <p role="status">現在の練習を確認しています…</p>
      ) : session.error ? (
        <ErrorView error={session.error} retry={() => void session.refetch()} />
      ) : (
        <>
          {canRetry ? (
            <MascotCoachCard
              variant="retry"
              heading={<h2>次の練習へ</h2>}
              actions={
                <>
                  <Link
                    href={`/practice/session/?sessionId=${feedback.sessionId}&mode=retry&fromAttemptId=${feedback.attemptId}`}
                  >
                    同じ質問に再挑戦
                  </Link>
                  <Button onClick={next}>次の質問へ</Button>
                </>
              }
            >
              <p>
                改善ポイントを意識して同じ質問に再挑戦するか、次の質問へ進みましょう。
              </p>
            </MascotCoachCard>
          ) : (
            <Actions>
              {current(session.data) || recovering ? (
                <Button onClick={next} disabled={mutation.isPending}>
                  {mutation.isPending
                    ? "次の質問を準備しています…"
                    : recovering
                      ? "次の質問の取得結果を再確認"
                      : "次の質問へ"}
                </Button>
              ) : (
                <Link
                  href={`/practice/session/?sessionId=${feedback.sessionId}`}
                >
                  現在の練習へ戻る
                </Link>
              )}
            </Actions>
          )}
          <Actions>
            <Link href="/practice/">新しい練習を始める</Link>
            <Link href="/">練習を終了</Link>
          </Actions>
        </>
      )}
      {mutation.error && <ErrorView error={mutation.error} />}
    </>
  );
};
