/** @file page.tsx @description 結果の静的ルート */
import { Suspense } from "react";
import { FeedbackResult } from "@/features/feedback/components/pages/FeedbackResult";
export default function ResultPage() {
  return (
    <Suspense fallback={<p role="status">結果を読み込んでいます…</p>}>
      <FeedbackResult />
    </Suspense>
  );
}
