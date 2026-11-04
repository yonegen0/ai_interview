/** @file page.tsx @description ログインの静的ルート。 */
import { Suspense } from "react";
import { LoginPage } from "@/features/auth/components/pages/LoginPage";
import { Text } from "@/components/atoms/Text";
export default function Page() {
  return (
    <Suspense fallback={<Text role="status">読み込んでいます…</Text>}>
      <LoginPage />
    </Suspense>
  );
}
