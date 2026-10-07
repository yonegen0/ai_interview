/** @file AccountActions.tsx @description Presentation and composition for AccountActions. */
"use client";
import { useAccountActions } from "@/hooks/useAccountActions";
import { AccountActionsView } from "./AccountActionsView";
export const AccountActions = () => (
  <AccountActionsView {...useAccountActions()} />
);
