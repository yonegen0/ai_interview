/** @file FeedbackResultTemplate.tsx @description Presentation and composition for FeedbackResultTemplate. */
"use client";
import { useState } from "react";
import type { Feedback } from "@/lib/api/schemas";
import { isFeedbackV2 } from "@/lib/api/schemas";
import { CoachingResponse } from "../organisms/CoachingResponse";
import { FeedbackCard } from "../organisms/FeedbackCard";
import {
  FeedbackNavigation,
  type FeedbackNavigationProps,
} from "../organisms/FeedbackNavigation";
export function FeedbackResultTemplate({
  feedback,
  ...navigation
}: FeedbackNavigationProps & { feedback: Feedback }) {
  const [canJumpToCoaching, setCanJumpToCoaching] = useState(false);
  return (
    <>
      <FeedbackCard feedback={feedback} canJumpToCoaching={canJumpToCoaching} />
      {isFeedbackV2(feedback) && feedback.result.status === "coaching" && (
        <CoachingResponse feedback={feedback} onAvailabilityChange={setCanJumpToCoaching} />
      )}
      <FeedbackNavigation {...navigation} />
    </>
  );
}
