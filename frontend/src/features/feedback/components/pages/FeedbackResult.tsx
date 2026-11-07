/** @file FeedbackResult.tsx @description Presentation and composition for FeedbackResult. */
"use client";
import type { Feedback, FollowUpReviewItem } from "@/lib/api/schemas";
import { Text } from "@/components/atoms/Text";
import { ErrorView } from "@/components/organisms/ErrorView";
import { useFeedbackResult } from "../../hooks/useFeedbackResult";
import { useFeedbackNavigation } from "../../hooks/useFeedbackNavigation";
import { FeedbackResultTemplate } from "../templates/FeedbackResultTemplate";
export const FeedbackResultContent = ({
  feedback, followUpReviews = [],
}: { feedback: Feedback; followUpReviews?: FollowUpReviewItem[] }) => (
  <FeedbackResultTemplate
    feedback={feedback}
    followUpReviews={followUpReviews}
    {...useFeedbackNavigation(feedback)}
  />
);
export function FeedbackResult() {
  const { contextKey, view, feedback, followUpReviews, actions } = useFeedbackResult();
  if (view.error)
    return <ErrorView error={view.error} retry={actions.refresh} />;
  if (view.loading) return <Text role="status">結果を読み込んでいます…</Text>;
  return feedback ? (
    <FeedbackResultContent key={contextKey} feedback={feedback} followUpReviews={followUpReviews} />
  ) : null;
}
