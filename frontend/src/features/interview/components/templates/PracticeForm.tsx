/** @file PracticeForm.tsx @description 質問・回答・評価・終了操作を構成する練習Template。 */
"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { styled } from "@mui/material/styles";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import type { Session } from "@/lib/api/schemas";
import { Actions } from "@/components/atoms/Actions";
import { Button } from "@/components/atoms/Button";
import { Link } from "@/components/atoms/Link";
import { Panel } from "@/components/atoms/Panel";
import { Dialog } from "@/components/organisms/Dialog";
import { ErrorView } from "@/components/organisms/ErrorView";
import { AnswerField } from "@/features/interview/components/molecules/AnswerField";
import { QuestionCard } from "@/features/interview/components/molecules/QuestionCard";
import { EvaluationLoading } from "@/features/interview/components/organisms/EvaluationLoading";
import { useAnswer } from "@/features/interview/hooks/useAnswer";
import type { EvaluationTiming } from "@/features/interview/hooks/useEvaluation";

const FailureCard = styled(MascotCoachCard)({ marginBottom: 24 });
const SubmissionCard = styled(MascotCoachCard)({ marginTop: 24 });

export type PracticeFormProps = {
  session: Session;
  retryFrom: string | null;
  timing?: EvaluationTiming;
};

export const PracticeForm = (props: PracticeFormProps) => {
  const state = useAnswer(props.session, props.retryFrom, props.timing);
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const navigated = useRef<string | null>(null);
  useEffect(() => {
    const data = state.evaluation.data;
    if (data?.status === "completed" && navigated.current !== data.attemptId) {
      navigated.current = data.attemptId;
      router.push(`/result/?attemptId=${data.attemptId}`);
    }
  }, [state.evaluation.data, router]);
  const exit = () => {
    state.discard();
    router.push("/practice/");
  };
  return (
    <>
      <h1>一問一答</h1>
      <QuestionCard
        question={props.session.question}
        number={props.session.questionNumber}
      />
      {state.phase === "processing" || state.phase === "completed" ? (
        <EvaluationLoading
          elapsed={state.evaluation.elapsed}
          paused={state.evaluation.paused}
          error={state.evaluation.error}
          retry={() => void state.evaluation.refetch()}
          longWaitSeconds={props.timing?.longWaitSeconds}
        />
      ) : state.phase === "failed" ? (
        <FailureCard
          variant="error"
          tone="attention"
          heading={<h2>評価の作成に失敗しました</h2>}
          actions={<Button onClick={state.retry}>同じ質問に再挑戦</Button>}
        >
          <p>もう一度、同じ質問に回答して練習できます。</p>
        </FailureCard>
      ) : (
        <Panel>
          <form
            onSubmit={state.form.handleSubmit((value) => state.send(value))}
          >
            <AnswerField
              field={state.form.register("answer")}
              count={state.answer.length}
              disabled={state.phase !== "answering"}
              error={state.form.formState.errors.answer?.message}
            />
            {state.phase === "submitting" ? (
              <SubmissionCard
                variant="thinking"
                heading={<h2>回答を送信しています</h2>}
                actions={
                  <Button type="submit" disabled>
                    回答を送信しています…
                  </Button>
                }
              >
                <p role="status" aria-live="polite">
                  送信が終わるまで、このままお待ちください。
                </p>
              </SubmissionCard>
            ) : (
              <Actions>
                {state.phase === "recovery_required" ? (
                  <Button type="button" onClick={() => void state.send()}>
                    送信結果を再確認
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    disabled={
                      !state.form.formState.isValid ||
                      state.phase !== "answering"
                    }
                  >
                    回答を送信
                  </Button>
                )}
              </Actions>
            )}
          </form>
          {state.error && <ErrorView error={state.error} />}
        </Panel>
      )}
      <Actions>
        <Button
          onClick={() =>
            state.answer || state.phase !== "answering"
              ? setConfirm(true)
              : exit()
          }
        >
          練習を終了
        </Button>
      </Actions>
      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title="練習を終了しますか？"
        content={
          <p>入力中の下書きは破棄されます。送信済みの評価は中止されません。</p>
        }
        actions={
          <>
            <Button autoFocus onClick={() => setConfirm(false)}>
              続ける
            </Button>
            {state.phase === "recovery_required" ||
            state.phase === "submitting" ? (
              <Link href="/practice/">未確定の送信を保持して終了</Link>
            ) : (
              <Button onClick={exit}>終了する</Button>
            )}
          </>
        }
      />
    </>
  );
};
