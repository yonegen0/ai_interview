/** @file HistoryAccountControls.tsx @description 共通アカウントUIと履歴Featureを上位で合成する。 */
"use client";
import { useEffect, useState } from "react";
import { AccountActions } from "@/components/molecules/AccountActions";
import { useAuthSession } from "@/hooks/useAuthSession";
import { HistoryDialog } from "./HistoryDialog";

export function HistoryAccountControls() {
  const [open, setOpen] = useState(false);
  const { sub } = useAuthSession();
  useEffect(() => { setOpen(false); }, [sub]);
  return (
    <>
      <AccountActions onHistory={() => setOpen(true)} />
      <HistoryDialog open={open && Boolean(sub)} owner={sub ?? ""} onClose={() => setOpen(false)} />
    </>
  );
}
