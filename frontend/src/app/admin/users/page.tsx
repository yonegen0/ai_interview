/** @file page.tsx @description Static-export ADMIN user history route. */
import { Suspense } from "react";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { AdminUserManagement } from "@/features/admin/components/pages/AdminUserManagement";
import { Text } from "@/components/atoms/Text";

export default function Page() {
  return (
    <Suspense fallback={<Text role="status">読み込んでいます…</Text>}>
      <AuthBoundary admin><AdminUserManagement /></AuthBoundary>
    </Suspense>
  );
}
