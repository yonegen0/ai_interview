/** @file useOperationScope.ts @description マウント時の利用者へ保存操作を束縛し、遅延応答を遮断する。 */
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { auth } from "@/lib/auth/session";
import { recoveryForScope } from "@/lib/storage/recovery";
import { ApiError } from "@/lib/api/client";
export function useOperationScope() {
  const [owner] = useState(() => {
    const scope = auth.scope();
    return {
      scope,
      generation: auth.generation(),
      storage: recoveryForScope(scope),
    };
  });
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const isActive = useCallback(
    () =>
      mounted.current &&
      auth.scope() === owner.scope &&
      auth.generation() === owner.generation,
    [owner.scope, owner.generation],
  );
  const assertActive = useCallback(() => {
    if (!isActive()) throw new ApiError("UNAUTHORIZED", 401);
  }, [isActive]);
  return { ...owner, isActive, assertActive };
}
