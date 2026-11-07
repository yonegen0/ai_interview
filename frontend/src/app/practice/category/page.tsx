/** Dedicated category selection route; existing /practice/ remains available. */
import { Suspense } from "react";
import { PracticeStart } from "@/features/interview/components/pages/PracticeStart";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { Text } from "@/components/atoms/Text";

export default function CategoryPage() {
  return (
    <Suspense fallback={<Text role="status">読み込んでいます…</Text>}>
      <AuthBoundary><PracticeStart categoryOnly /></AuthBoundary>
    </Suspense>
  );
}
