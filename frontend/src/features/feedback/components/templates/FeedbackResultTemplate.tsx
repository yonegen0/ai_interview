/** @file FeedbackResultTemplate.tsx @description Presentation and composition for FeedbackResultTemplate. */
"use client";
import { useState } from "react";
import type { Feedback, FollowUpReviewItem } from "@/lib/api/schemas";
import { isFeedbackV2 } from "@/lib/api/schemas";
import { CoachingResponse } from "../organisms/CoachingResponse";
import { FeedbackCard } from "../organisms/FeedbackCard";
import {
  FeedbackNavigation,
  type FeedbackNavigationProps,
} from "../organisms/FeedbackNavigation";
export function FeedbackResultTemplate({
  feedback,
  followUpReviews = [],
  ...navigation
}: FeedbackNavigationProps & { feedback: Feedback; followUpReviews?: FollowUpReviewItem[] }) {
  const [canJumpToCoaching, setCanJumpToCoaching] = useState(false);
  return (
    <>
      <FeedbackCard feedback={feedback} followUpReviews={followUpReviews} canJumpToCoaching={canJumpToCoaching} />
      {isFeedbackV2(feedback) && feedback.result.status === "coaching" && (
        <CoachingResponse feedback={feedback} onAvailabilityChange={setCanJumpToCoaching} />
      )}
      <FeedbackNavigation {...navigation} />
    </>
  );
}
