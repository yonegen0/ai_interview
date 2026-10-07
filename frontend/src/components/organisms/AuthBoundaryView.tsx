/** @file AuthBoundaryView.tsx @description Presentation and composition for AuthBoundaryView. */
"use client";
import type { ReactNode } from "react";
import { Text } from "@/components/atoms/Text";
import { Link } from "@/components/atoms/Link";
export type AuthBoundaryViewProps = {
  children: ReactNode;
  status: "restoring" | "anonymous" | "forbidden" | "allowed";
  error?: string;
  loginUrl: string;
};
export function AuthBoundaryView({
  children,
  status,
  error,
  loginUrl,
}: AuthBoundaryViewProps) {
  if (status === "restoring")
    return <Text role="status">ログイン状態を確認しています…</Text>;
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
