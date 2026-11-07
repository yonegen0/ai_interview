/** @file AuthBoundaryView.tsx @description Presentation and composition for AuthBoundaryView. */
"use client";
import { Activity, type ReactNode } from "react";
import { Text } from "@/components/atoms/Text";
import { Link } from "@/components/atoms/Link";
import { Button } from "@/components/atoms/Button";
export type AuthBoundaryViewProps = {
  children: ReactNode;
  status: "restoring" | "temporarily_unavailable" | "anonymous" | "forbidden" | "allowed";
  error?: string;
  loginUrl: string;
  onRetry?: () => void;
  preserveMounted?: boolean;
};
export function AuthBoundaryView({
  children,
  status,
  error,
  loginUrl,
  onRetry,
  preserveMounted = false,
}: AuthBoundaryViewProps) {
  return (
    <>
      {status === "restoring" && <Text role="status">ログイン状態を確認しています…</Text>}
      {status === "temporarily_unavailable" && (
        <>
          <Text role="status">{error || "通信の問題で認証を確認できません。接続を確認して再度お試しください。"}</Text>
          {onRetry && <Button type="button" variant="outlined" onClick={onRetry}>認証を再確認する</Button>}
        </>
      )}
      {status === "anonymous" && (
        <>
          <Text>{error || "ログインして練習を始めましょう。"}</Text>
          <Link href={loginUrl}>ログイン</Link>
        </>
      )}
      {status === "forbidden" && <Text role="alert">この操作を行う権限がありません。</Text>}
      {(status === "allowed" || preserveMounted) && (
        // Activity hides unverified content and pauses effects without discarding input state.
        <Activity mode={status === "allowed" ? "visible" : "hidden"}>
          {children}
        </Activity>
      )}
    </>
  );
}
