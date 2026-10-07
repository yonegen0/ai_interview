/** @file FeedbackResult.tsx @description Presentation and composition for FeedbackResult. */
"use client";
import type { Feedback } from "@/lib/api/schemas";
import { Text } from "@/components/atoms/Text";
import { ErrorView } from "@/components/organisms/ErrorView";
import { useFeedbackResult } from "../../hooks/useFeedbackResult";
import { useFeedbackNavigation } from "../../hooks/useFeedbackNavigation";
import { FeedbackResultTemplate } from "../templates/FeedbackResultTemplate";
export const FeedbackResultContent = ({ feedback }: { feedback: Feedback }) => (
  <FeedbackResultTemplate
    feedback={feedback}
    {...useFeedbackNavigation(feedback)}
  />
);
export function FeedbackResult() {
  const { contextKey, view, feedback, actions } = useFeedbackResult();
  if (view.error)
    return <ErrorView error={view.error} retry={actions.refresh} />;
  if (view.loading) return <Text role="status">結果を読み込んでいます…</Text>;
  return feedback ? (
    <FeedbackResultContent key={contextKey} feedback={feedback} />
  ) : null;
}
