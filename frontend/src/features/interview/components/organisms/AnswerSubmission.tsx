/** @file AnswerSubmission.tsx @description Presentation and composition for AnswerSubmission. */
"use client";
import { StarAssistPanel } from "@/features/starAssist/components/organisms/StarAssistPanel";
import { styled } from "@mui/material/styles";
import { Panel } from "@/components/atoms/Panel";
import { Actions } from "@/components/atoms/Actions";
import { Button } from "@/components/atoms/Button";
import { Text } from "@/components/atoms/Text";
import { MascotCoachCard } from "@/components/molecules/MascotCoachCard";
import { ErrorView } from "@/components/organisms/ErrorView";
import { AnswerField } from "../molecules/AnswerField";
import type { AnswerSubmissionProps } from "../../model/practice";
const SubmissionCard = styled(MascotCoachCard)(({ theme }) => ({
  marginTop: theme.spacing(3),
}));
export const AnswerSubmission = ({
  workspace,
  previousAnswer,
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
}: AnswerSubmissionProps) => (
  <Panel>
    {phase === "answering" && previousAnswer !== undefined && (
      <Text>
        前回回答から修正できます。正式送信するまで回答履歴は増えません。
      </Text>
    )}
    {phase === "answering" && (
      <Actions>
        {previousAnswer !== undefined && (
          <Button type="button" onClick={onRestorePrevious}>
            前回回答に戻す
          </Button>
        )}
        {onClear && (
          <Button type="button" onClick={onClear}>
            入力をクリア
          </Button>
        )}
      </Actions>
    )}
    {phase === "answering" && workspace && (
      <StarAssistPanel workspace={workspace} hasAnswer={count > 0} />
    )}
    <form onSubmit={onSubmit}>
      <AnswerField
        field={field}
        count={count}
        disabled={phase !== "answering"}
        error={inputError}
      />
      {phase === "submitting" ? (
        <SubmissionCard
          variant="thinking"
          heading={
            <Text variant="h2" component="h2">
              回答を送信しています
            </Text>
          }
          actions={
            <Button variant="contained" color="primary" type="submit" disabled>
              回答を送信しています…
            </Button>
          }
        >
          <Text role="status" aria-live="polite">
            送信が終わるまで、このままお待ちください。
          </Text>
        </SubmissionCard>
      ) : (
        <Actions>
          {phase === "recovery_required" ? (
            <Button
              variant="contained"
              color="primary"
              type="button"
              onClick={onReconfirm}
            >
              送信結果を再確認
            </Button>
          ) : (
            <Button
              variant="contained"
              color="primary"
              type="submit"
              disabled={!valid || phase !== "answering"}
            >
              回答を送信
            </Button>
          )}
        </Actions>
      )}
    </form>
    {error && <ErrorView error={error} />}
  </Panel>
);
