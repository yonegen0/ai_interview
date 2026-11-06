/** @file AccountActions.tsx @description 共通メニューと認証状態、アカウント管理Dialogを接続する。 */
"use client";

import { useEffect, useRef, useState } from "react";
import { AccountActionsView } from "@/components/molecules/AccountActionsView";
import { AccountManagementDialog } from "@/components/organisms/AccountManagementDialog";
import { useAccountActions } from "@/hooks/useAccountActions";

type HistoryTab = 0 | 1;

export function AccountActions({ onHistory }: { onHistory?: (tab: HistoryTab) => void }) {
  const account = useAccountActions();
  const [dialogOwner, setDialogOwner] = useState<string | null>(null);
  const pending = useRef<{ owner: string; tab: HistoryTab } | null>(null);
  const currentOwner = useRef(account.sub);
  useEffect(() => {
    currentOwner.current = account.sub;
    pending.current = null;
    setDialogOwner(null);
  }, [account.sub]);

  const requestHistory = (tab: HistoryTab) => {
    if (!account.sub || !onHistory) return;
    if (dialogOwner === account.sub) {
      pending.current = { owner: account.sub, tab };
      setDialogOwner(null);
    } else {
      onHistory(tab);
    }
  };

  const logout = () => {
    pending.current = null;
    setDialogOwner(null);
    account.onLogout();
  };

  const handleExited = () => {
    const next = pending.current;
    pending.current = null;
    if (next && next.owner === currentOwner.current) onHistory?.(next.tab);
  };

  return (
    <>
      <AccountActionsView {...account} onLogout={logout}
        onHistory={onHistory ? () => requestHistory(0) : undefined}
        onManage={() => { if (account.sub) setDialogOwner(account.sub); }} />
      <AccountManagementDialog
        open={Boolean(dialogOwner && dialogOwner === account.sub)}
        admin={account.admin}
        sub={account.sub}
        phase={account.phase}
        onClose={() => { pending.current = null; setDialogOwner(null); }}
        onHistory={onHistory ? requestHistory : undefined}
        onLogout={logout}
        onExited={handleExited}
      />
    </>
  );
}
