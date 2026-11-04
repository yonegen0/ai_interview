/** @file page.tsx @description 結果の静的ルート */
import { Suspense } from "react";
import { FeedbackResult } from "@/features/feedback/components/pages/FeedbackResult";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { Text } from "@/components/atoms/Text";
export default function ResultPage() {
  return (
    <Suspense fallback={<Text role="status">結果を読み込んでいます…</Text>}>
      <AuthBoundary>
        <FeedbackResult />
      </AuthBoundary>
    </Suspense>
  );
}
