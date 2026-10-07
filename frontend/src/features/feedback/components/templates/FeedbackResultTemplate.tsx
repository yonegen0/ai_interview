/** @file FeedbackResultTemplate.tsx @description Presentation and composition for FeedbackResultTemplate. */
"use client";
import type { Feedback } from "@/lib/api/schemas";
import { FeedbackCard } from "../organisms/FeedbackCard";
import {
  FeedbackNavigation,
  type FeedbackNavigationProps,
} from "../organisms/FeedbackNavigation";
export const FeedbackResultTemplate = ({
  feedback,
  ...navigation
}: FeedbackNavigationProps & { feedback: Feedback }) => (
  <>
    <FeedbackCard feedback={feedback} />
    <FeedbackNavigation {...navigation} />
  </>
);
