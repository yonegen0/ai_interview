/** Quick start route: no question picker or confirmation dialog. */
import { Suspense } from "react";
import { PracticeQuick } from "@/features/interview/components/pages/PracticeQuick";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { Text } from "@/components/atoms/Text";

export default function QuickPage() {
  return (
    <Suspense fallback={<Text role="status">読み込んでいます…</Text>}>
      <AuthBoundary><PracticeQuick /></AuthBoundary>
    </Suspense>
  );
}
