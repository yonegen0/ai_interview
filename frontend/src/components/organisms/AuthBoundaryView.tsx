/** @file AuthBoundaryView.tsx @description Presentation and composition for AuthBoundaryView. */
"use client";
import type { ReactNode } from "react";
import { Text } from "@/components/atoms/Text";
import { Link } from "@/components/atoms/Link";
import { Button } from "@/components/atoms/Button";
export type AuthBoundaryViewProps = {
  children: ReactNode;
  status: "restoring" | "temporarily_unavailable" | "anonymous" | "forbidden" | "allowed";
  error?: string;
  loginUrl: string;
  onRetry?: () => void;
};
export function AuthBoundaryView({
  children,
  status,
  error,
  loginUrl,
  onRetry,
}: AuthBoundaryViewProps) {
  if (status === "restoring")
    return <Text role="status">ログイン状態を確認しています…</Text>;
  if (status === "temporarily_unavailable")
    return (
      <>
        <Text role="status">{error || "通信の問題で認証状態を確認できません。再接続後に確認します。"}</Text>
        {onRetry && <Button type="button" variant="outlined" onClick={onRetry}>認証を再確認する</Button>}
      </>
    );
  if (status === "anonymous")
    return (
      <>
        <Text>{error || "ログインして練習を始めましょう。"}</Text>
        <Link href={loginUrl}>ログイン</Link>
      </>
    );
  if (status === "forbidden")
    return <Text role="alert">この操作を行う権限がありません。</Text>;
  return <>{children}</>;
}
