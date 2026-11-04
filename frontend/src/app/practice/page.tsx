/** @file page.tsx @description 練習開始の静的ルート */
import { PracticeStart } from "@/features/interview/components/pages/PracticeStart";
import { Suspense } from "react";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { Text } from "@/components/atoms/Text";
export default function PracticePage() {
  return (
    <Suspense fallback={<Text role="status">読み込んでいます…</Text>}>
      <AuthBoundary>
        <PracticeStart />
      </AuthBoundary>
    </Suspense>
  );
}
