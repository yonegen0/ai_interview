/** @file page.tsx @description 練習開始の静的ルート */
import { PracticeStart } from "@/features/interview/components/pages/PracticeStart";
import { Suspense } from "react";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
export default function PracticePage() {
  return (
    <Suspense fallback={<p role="status">読み込んでいます…</p>}>
      <AuthBoundary>
        <PracticeStart />
      </AuthBoundary>
    </Suspense>
  );
}
