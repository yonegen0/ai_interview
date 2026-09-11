/** @file page.tsx @description URLクエリをClientで解釈する静的練習ルート */
import { Suspense } from "react";
import { InterviewPractice } from "@/features/interview/components/pages/InterviewPractice";
export default function SessionPage() {
  return (
    <Suspense fallback={<p role="status">練習を読み込んでいます…</p>}>
      <InterviewPractice />
    </Suspense>
  );
}
