/** @file HistoryAccountControls.tsx @description 既存アカウントメニューと本人別の履歴Dialogを合成する。 */
"use client";
import { useEffect, useState } from "react";
import { AccountActions } from "@/components/organisms/AccountActions";
import { useAuthSession } from "@/hooks/useAuthSession";
import { HistoryDialog, type HistoryTab } from "./HistoryDialog";

type HistoryView = { owner: string; tab: HistoryTab };

export function HistoryAccountControls() {
  const [view, setView] = useState<HistoryView | null>(null);
  const { sub } = useAuthSession();

  useEffect(() => { setView(null); }, [sub]);

  const openHistory = (tab: HistoryTab) => {
    if (sub) setView({ owner: sub, tab });
  };

  const visible = Boolean(view && sub && view.owner === sub);
  return (
    <>
      <AccountActions onHistory={openHistory} />
      {visible && view && (
        <HistoryDialog
          open
          owner={view.owner}
          initialTab={view.tab}
          onClose={() => setView(null)}
        />
      )}
    </>
  );
}
