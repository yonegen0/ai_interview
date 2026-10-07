/** @file PracticeForm.tsx @description Presentation and composition for PracticeForm. */
"use client";
import { Text } from "@/components/atoms/Text";
import { Header } from "@/components/molecules/Header";
import { Button } from "@/components/atoms/Button";
import { Link } from "@/components/atoms/Link";
import { Actions } from "@/components/atoms/Actions";
import { Dialog } from "@/components/organisms/Dialog";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { QuestionCard } from "../molecules/QuestionCard";
import { EvaluationLoading } from "../organisms/EvaluationLoading";
import { AnswerSubmission } from "../organisms/AnswerSubmission";
import { exitNotice } from "../../model/practice";
import type {
  PracticeView,
  PracticeActions,
  AnswerSubmissionProps,
} from "../../model/practice";
export type PracticeFormProps = {
  view: PracticeView;
  form: AnswerSubmissionProps;
  actions: PracticeActions;
};
export const PracticeForm = ({ view, form, actions }: PracticeFormProps) => (
  <>
    <Header title="一問一答" />
    <QuestionCard
      question={view.session.question}
      number={view.session.questionNumber}
      total={
        view.session.mode === "legacy" ? undefined : view.session.totalQuestions
      }
    />
    {view.phase === "processing" || view.phase === "completed" ? (
      <EvaluationLoading
        elapsed={view.elapsed}
        paused={view.paused}
        error={view.evaluationError}
        retry={actions.refreshEvaluation}
        longWaitSeconds={view.longWaitSeconds}
      />
    ) : view.phase === "failed" ? (
      <MascotCoachCard
        variant="error"
        tone="attention"
        heading={
          <Text variant="h2" component="h2">
            評価の作成に失敗しました
          </Text>
        }
        actions={
          <Button variant="contained" color="primary" onClick={actions.retry}>
            同じ質問に再挑戦
          </Button>
        }
      >
        <Text>もう一度、同じ質問に回答して練習できます。</Text>
      </MascotCoachCard>
    ) : (
      <AnswerSubmission {...form} />
    )}
    <Actions>
      <Button variant="text" color="inherit" onClick={actions.requestExit}>
        練習を終了
      </Button>
    </Actions>
    <Dialog
      open={view.confirm}
      onClose={actions.closeExit}
      title="練習を終了しますか？"
      content={<Text>{exitNotice(view.phase)}</Text>}
      actions={
        <>
          <Button
            variant="outlined"
            color="primary"
            autoFocus
            onClick={actions.closeExit}
          >
            続ける
          </Button>
          {view.phase === "recovery_required" || view.phase === "submitting" ? (
            <Link href="/practice/">未確定の送信を保持して終了</Link>
          ) : (
            <Button variant="contained" color="error" onClick={actions.exit}>
              終了する
            </Button>
          )}
        </>
      }
    />
  </>
);
