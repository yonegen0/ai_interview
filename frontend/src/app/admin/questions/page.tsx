/** @file page.tsx @description ADMIN専用の質問管理ルート。 */
import { Suspense } from "react";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { QuestionManagement } from "@/features/admin/components/pages/QuestionManagement";
export default function Page() {
  return (
    <Suspense fallback={<p role="status">読み込んでいます…</p>}>
      <AuthBoundary admin>
        <QuestionManagement />
      </AuthBoundary>
    </Suspense>
  );
}
