/** @file AccountActionsView.tsx @description Presentation and composition for AccountActionsView. */
"use client";
import { Button } from "@/components/atoms/Button";
import { Link } from "@/components/atoms/Link";
export type AccountActionsViewProps = {
  authenticated: boolean;
  admin?: boolean;
  onLogout: () => void;
};
export const AccountActionsView = ({
  authenticated,
  admin,
  onLogout,
}: AccountActionsViewProps) => (
  <nav aria-label="アカウント">
    {authenticated ? (
      <>
        {admin && <Link href="/admin/questions/">質問管理</Link>}{" "}
        <Button variant="text" color="inherit" type="button" onClick={onLogout}>
          ログアウト
        </Button>
      </>
    ) : (
      <Link href="/login/">ログイン</Link>
    )}
  </nav>
);
