/** @file page.tsx @description ADMIN専用の質問管理ルート。 */
import { Suspense } from "react";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { QuestionManagement } from "@/features/admin/components/pages/QuestionManagement";
import { Text } from "@/components/atoms/Text";
export default function Page() {
  return (
    <Suspense fallback={<Text role="status">読み込んでいます…</Text>}>
      <AuthBoundary admin>
        <QuestionManagement />
      </AuthBoundary>
    </Suspense>
  );
}
