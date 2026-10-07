/** @file usePracticeStart.ts @description State and side-effect controller for usePracticeStart. */
"use client";
import { useOperationScope } from "@/hooks/useOperationScope";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  createSchema,
  type Category,
  type CreateInput,
} from "@/lib/api/schemas";
import { createSession, getPracticeOptions } from "@/lib/api/interview";
import { ApiError, uncertain } from "@/lib/api/client";
import { operationSchema } from "@/lib/storage/recovery";
import type {
  PracticeStartView,
  PracticeStartActions,
} from "../model/practiceStart";
export function usePracticeStart() {
  const {
    scope,
    isActive,
    assertActive,
    storage: { readSaved, save, removeSaved },
  } = useOperationScope();
  const router = useRouter();
  const [category, setCategory] = useState<Category | null>(null);
  const [mode, setMode] = useState<"full" | "category">("full");
  const options = useQuery({
    queryKey: [scope, "practice-options"],
    queryFn: ({ signal }) => {
      assertActive();
      return getPracticeOptions(signal);
    },
    enabled: isActive(),
  });
  const pending = useRef<ReturnType<typeof operationSchema.parse> | null>(null);
  const [recovering, setRecovering] = useState(false);
  const [restoring, setRestoring] = useState(true);
  useEffect(() => {
    if (!isActive()) return;
    const restored = readSaved("pocket:create", operationSchema);
    if (restored?.body || restored?.category) {
      pending.current = restored;
      setCategory(
        restored.body && "category" in restored.body
          ? restored.body.category!
          : restored.category || null,
      );
      setMode(restored.body?.mode || "category");
      setRecovering(true);
    }
    setRestoring(false);
  }, [readSaved, isActive]);
  const locked = useRef(false);
  const mutation = useMutation({
    mutationFn: ({ body, key }: { body: CreateInput; key: string }) => {
      assertActive();
      return createSession(body, key);
    },
  });
  const start = async () => {
    if (
      !isActive() ||
      locked.current ||
      (!pending.current && mode === "category" && !category)
    )
      return;
    locked.current = true;
    const request = pending.current ?? {
      version: 1 as const,
      key: crypto.randomUUID(),
      body: createSchema.parse(
        mode === "full"
          ? { mode, difficulty: "standard" }
          : { mode, category, difficulty: "standard" },
      ),
    };
    pending.current = request;
    save("pocket:create", request);
    try {
      const value = await mutation.mutateAsync({
        body:
          request.body ||
          createSchema.parse({
            category: request.category,
            difficulty: "standard",
          }),
        key: request.key,
      });
      if (!isActive()) return;
      removeSaved("pocket:create");
      router.push(`/practice/session/?sessionId=${value.sessionId}`);
    } catch (error) {
      if (!isActive()) return;
      if (uncertain(error)) setRecovering(true);
      else {
        pending.current = null;
        removeSaved("pocket:create");
        setRecovering(false);
        if (
          error instanceof ApiError &&
          error.code === "CATEGORY_UNAVAILABLE"
        ) {
          setCategory(null);
          void options.refetch();
        }
      }
    } finally {
      locked.current = false;
    }
  };

  const disabled = restoring || mutation.isPending || recovering;
  return {
    view: {
      mode,
      category,
      options: options.data,
      loading: options.isPending,
      optionsError: options.error,
      error: mutation.error,
      disabled,
      canStart:
        !restoring &&
        !mutation.isPending &&
        (recovering || (!!options.data && (mode !== "category" || !!category))),
      starting: mutation.isPending,
      recovering,
    } satisfies PracticeStartView,
    actions: {
      selectMode: (value) => {
        if (isActive() && !disabled) setMode(value);
      },
      selectCategory: (value) => {
        if (isActive() && !disabled) setCategory(value);
      },
      start,
      refresh: () => {
        if (isActive()) void options.refetch();
      },
    } satisfies PracticeStartActions,
  };
}
