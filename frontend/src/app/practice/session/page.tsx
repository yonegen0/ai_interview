/** @file page.tsx @description URLクエリをClientで解釈する静的練習ルート */
import { Suspense } from "react";
import { InterviewPractice } from "@/features/interview/components/pages/InterviewPractice";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { Text } from "@/components/atoms/Text";
export default function SessionPage() {
  return (
    <Suspense fallback={<Text role="status">練習を読み込んでいます…</Text>}>
      <AuthBoundary>
        <InterviewPractice />
      </AuthBoundary>
    </Suspense>
  );
}
