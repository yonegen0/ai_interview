/** @file page.tsx @description ログインの静的ルート。 */
import { Suspense } from "react";
import { LoginPage } from "@/features/auth/components/pages/LoginPage";
export default function Page() {
  return (
    <Suspense fallback={<p role="status">読み込んでいます…</p>}>
      <LoginPage />
    </Suspense>
  );
}
