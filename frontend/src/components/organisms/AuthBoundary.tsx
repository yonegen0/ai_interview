/** @file AuthBoundary.tsx @description Presentation and composition for AuthBoundary. */
"use client";
import type { ReactNode } from "react";
import { useAuthBoundary } from "@/hooks/useAuthBoundary";
import { AuthBoundaryView } from "./AuthBoundaryView";
export function AuthBoundary({
  children,
  admin = false,
}: {
  children: ReactNode;
  admin?: boolean;
}) {
  const { ownerKey, ...view } = useAuthBoundary(admin);
  return (
    <AuthBoundaryView key={ownerKey} {...view}>
      {children}
    </AuthBoundaryView>
  );
}
