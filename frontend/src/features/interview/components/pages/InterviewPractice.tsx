/** @file InterviewPractice.tsx @description Presentation and composition for InterviewPractice. */
"use client";
import { Text } from "@/components/atoms/Text";
import { Link } from "@/components/atoms/Link";
import { ErrorView } from "@/components/organisms/ErrorView";
import { usePracticeSession } from "../../hooks/usePracticeSession";
import { PracticeSessionContent } from "./PracticeSessionContent";
export function InterviewPractice() {
  const state = usePracticeSession();
  if (state.view.loading)
    return <Text role="status">{state.view.loading}</Text>;
  if (state.view.error)
    return (
      <>
        <ErrorView error={state.view.error} retry={state.refresh} />
        {state.view.returnUrl && (
          <Link href={state.view.returnUrl}>現在の練習へ戻る</Link>
        )}
      </>
    );
  if (!state.session) return null;
  return (
    <PracticeSessionContent
      key={state.contextKey}
      session={state.session}
      retryFrom={state.retryFrom}
    />
  );
}
