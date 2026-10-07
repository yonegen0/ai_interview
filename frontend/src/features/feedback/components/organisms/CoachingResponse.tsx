/** @file CoachingResponse.tsx @description Current-only follow-up answer form backed by Session state. */
"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useOperationScope } from "@/hooks/useOperationScope";
import { useAnswerOperation } from "@/hooks/useAnswerOperation";
import { getQuestion } from "@/lib/api/interview";
import type { FeedbackV2, Session } from "@/lib/api/schemas";
import { countCodePoints } from "@/lib/textLimits";
import { Text } from "@/components/atoms/Text";
import { Panel } from "@/components/atoms/Panel";
import { AnswerSubmission } from "@/features/interview/components/organisms/AnswerSubmission";

function CurrentResponse({
  feedback,
  session,
}: {
  feedback: FeedbackV2;
  session: Session;
}) {
  const { isActive } = useOperationScope();
  const router = useRouter();
  const state = useAnswerOperation(
    session,
    null,
    undefined,
    {
      kind: "coaching_answer",
      questionId: session.question.id,
      answer: "",
      attemptId: feedback.attemptId,
      fromEvaluationId: feedback.evaluationId,
    },
    (accepted) =>
      router.push(
        `/practice/session/?sessionId=${session.sessionId}&mode=evaluation&evaluationId=${accepted.evaluationId}`,
      ),
  );
  useEffect(() => {
    if (isActive() && state.evaluation.data?.status === "completed")
      router.push(
        `/result/?attemptId=${feedback.attemptId}&evaluationId=${state.evaluation.data.evaluationId}`,
      );
  }, [state.evaluation.data, router, feedback.attemptId, isActive]);
  return (
    <Panel>
      <Text variant="h2" component="h2">
        深掘り質問 {feedback.coachingCount + 1} / 3
      </Text>
      <Text>{feedback.result.follow_up_question}</Text>
      <AnswerSubmission
        field={state.form.register("answer")}
        count={countCodePoints(state.answer)}
        phase={state.phase}
        valid={state.form.formState.isValid}
        inputError={state.form.formState.errors.answer?.message}
        error={state.error}
        onSubmit={state.form.handleSubmit((value) => state.send(value))}
        onReconfirm={() => void state.send()}
      />
    </Panel>
  );
}

export function CoachingResponse({ feedback }: { feedback: FeedbackV2 }) {
  const { scope, isActive, assertActive } = useOperationScope();
  const query = useQuery({
    queryKey: [scope, "session", feedback.sessionId],
    queryFn: ({ signal }) => {
      assertActive();
      return getQuestion(feedback.sessionId, signal);
    },
    enabled: isActive(),
    refetchOnMount: "always",
  });
  const progress = query.data?.activeCoaching;
  if (query.isPending)
    return <Text role="status">現在の質問を確認しています…</Text>;
  if (query.error)
    return <Text role="alert">現在の質問を取得できませんでした。</Text>;
  if (
    !query.data ||
    progress?.stage !== "awaiting_answer" ||
    progress.evaluationId !== feedback.evaluationId ||
    progress.attemptId !== feedback.attemptId
  )
    return null;
  return (
    <CurrentResponse
      key={feedback.evaluationId}
      feedback={feedback}
      session={query.data}
    />
  );
}
