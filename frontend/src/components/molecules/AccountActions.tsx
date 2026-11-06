/** @file AccountActions.tsx @description アカウント操作を既存認証Hookと結合する。 */
"use client";
import { useAccountActions } from "@/hooks/useAccountActions";
import { AccountActionsView } from "./AccountActionsView";

export const AccountActions = ({ onHistory }: { onHistory?: () => void }) => (
  <AccountActionsView {...useAccountActions()} onHistory={onHistory} />
);
