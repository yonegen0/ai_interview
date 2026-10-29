/** @file useStarWorkspace.ts @description Owner-scoped server drafts, serial saves and explicit recovery. */
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useOperationScope } from "@/hooks/useOperationScope";
import { ApiError, uncertain } from "@/lib/api/client";
import {
  getDrafts,
  getGeneration,
  getPreferences,
  getQuota,
  getStarRequest,
  executeStarOperation,
} from "@/lib/api/star";
import {
  starInputSchema,
  starReceiptSchema,
  preferencesReceiptSchema,
  contextReceiptSchema,
  generationReceiptSchema,
  applyReceiptSchema,
  starOperationRecoverySchema,
  starValue,
  emptyStarInput,
  type StarContextInput,
  type StarInput,
  type StarOperation,
  type StarReceipt,
  type Drafts,
} from "@/lib/api/schemas/star";
import type { Session } from "@/lib/api/schemas";
import { canonical, sha256 } from "@/lib/jsonHash";

type SaveState = "未保存" | "保存中" | "保存済" | "保存失敗" | "競合";
const responseSchema = (op: StarOperation): z.ZodType<unknown> =>
  op.path.endsWith("/answer-contexts")
    ? contextReceiptSchema
    : op.path === "/star-assist/preferences"
      ? preferencesReceiptSchema
      : op.path === "/star-assist/generations"
        ? generationReceiptSchema
        : op.path.endsWith("/applications")
          ? applyReceiptSchema
          : starReceiptSchema;

const generationRecoverySchema = z.object({
  version: z.literal(1),
  generationId: z.uuid(),
}).strict();

export function useStarWorkspace(
  session: Session,
  origin: StarContextInput,
  answer: string,
  dirty: boolean,
  enabled: boolean,
  localCache: { draft: string; serverDraftId?: string } | null,
  restoreAnswer: (answer: string) => void,
) {
  const { scope, isActive, assertActive, storage } = useOperationScope();
  const contextBody = JSON.stringify(origin);
  const operationKey = `pocket:star:operation:${session.sessionId}:${contextBody}`;
  const generationKey = `pocket:star:generation:${session.sessionId}:${contextBody}`;
  const [contextRequestKey] = useState(() => crypto.randomUUID());
  const [pending, setPending] = useState<StarOperation | null>(() =>
    storage.readSaved(operationKey, starOperationRecoverySchema),
  );
  const [status, setStatus] = useState<SaveState>(
    pending ? "保存失敗" : "未保存",
  );
  const [error, setError] = useState<string | null>(null);
  const [savedPreview, setSavedPreview] = useState<string | null>(null);
  const [applicationId, setApplicationId] = useState<string | null>(null);
  const [answerCache, setAnswerCache] = useState<{
    id: string;
    expiresAt: number;
  } | null>(null);
  const [generationId, setGenerationId] = useState<string | null>(
    () => storage.readSaved(generationKey, generationRecoverySchema)?.generationId ?? null,
  );
  const rememberGeneration = (id: string) => {
    storage.save(generationKey, { version: 1, generationId: id });
    setGenerationId(id);
  };
  const [resultWaiting, setResultWaiting] = useState(false);
  const [generationCategory, setGenerationCategory] =
    useState<StarInput["targetCategory"]>(null);
  const form = useForm<StarInput>({
    resolver: zodResolver(starInputSchema),
    mode: "onChange",
    defaultValues: emptyStarInput(),
  });
  const watched = useWatch({ control: form.control });
  const input = starValue(
    starInputSchema.safeParse(watched).success
      ? (watched as StarInput)
      : form.getValues(),
  );
  const inputJson = JSON.stringify(input);
  const latest = useRef({ answer, input, dirty });
  useEffect(() => {
    latest.current = { answer, input, dirty };
  }, [answer, input, inputJson, dirty]);
  const answerMeta = useRef<StarReceipt | null>(null),
    starMeta = useRef<StarReceipt | null>(null);
  const answerBaseline = useRef(answer),
    starBaseline = useRef(JSON.stringify(emptyStarInput()));
  const initialized = useRef(false),
    locked = useRef(false),
    active = useRef(enabled);
  useEffect(() => {
    active.current = enabled;
  }, [enabled]);
  const editGeneration = useRef(0),
    previousText = useRef(answer);
  useEffect(() => {
    if (previousText.current !== answer) {
      editGeneration.current++;
      previousText.current = answer;
    }
  }, [answer]);
  const generatedFrom = useRef<string | null>(null),
    handledGeneration = useRef<string | null>(null);
  const mutation = useMutation({
    retry: false,
    mutationFn: (operation: StarOperation) => {
      assertActive();
      return executeStarOperation(operation, responseSchema(operation));
    },
  });
  const context = useQuery({
    queryKey: [scope, "star-context", session.sessionId, contextBody],
    retry: false,
    staleTime: Infinity,
    enabled: enabled && isActive(),
    queryFn: () => {
      assertActive();
      return executeStarOperation(
        {
          version: 1,
          key: contextRequestKey,
          path: `/sessions/${session.sessionId}/answer-contexts`,
          method: "POST",
          body: origin,
          contextId: null,
          editGeneration: 0,
        },
        contextReceiptSchema,
      );
    },
  });
  const contextId = context.data?.contextId ?? null;
  const drafts = useQuery({
    queryKey: [scope, "server-drafts", contextId],
    retry: false,
    enabled: !!contextId && enabled && isActive(),
    queryFn: ({ signal }) => {
      assertActive();
      return getDrafts(contextId!, signal);
    },
  });
  const preferences = useQuery({
    queryKey: [scope, "star-preferences"],
    retry: false,
    enabled: enabled && isActive(),
    queryFn: ({ signal }) => getPreferences(signal),
  });
  const quota = useQuery({
    queryKey: [scope, "star-quota"],
    retry: false,
    enabled: enabled && isActive(),
    queryFn: ({ signal }) => getQuota(signal),
  });
  const generation = useQuery({
    queryKey: [scope, "star-generation", generationId],
    retry: false,
    enabled: !!generationId && enabled && isActive(),
    queryFn: ({ signal }) => getGeneration(generationId!, signal),
    refetchInterval: (q) =>
      q.state.data &&
      !["QUEUED", "PREPARED", "STARTED"].includes(q.state.data.status)
        ? false
        : 1000,
  });

  const hydrate = useCallback(
    (value: Drafts, overwrite: boolean, overwriteStar = overwrite) => {
      answerMeta.current =
        value.answerDraft &&
        starReceiptSchema.parse({
          id: value.answerDraft.id,
          version: value.answerDraft.version,
          updatedAt: value.answerDraft.updatedAt,
          expiresAt: value.answerDraft.expiresAt,
        });
      setAnswerCache(
        value.answerDraft
          ? { id: value.answerDraft.id, expiresAt: value.answerDraft.expiresAt }
          : null,
      );
      starMeta.current =
        value.starDraft &&
        starReceiptSchema.parse({
          id: value.starDraft.id,
          version: value.starDraft.version,
          updatedAt: value.starDraft.updatedAt,
          expiresAt: value.starDraft.expiresAt,
        });
      answerBaseline.current = value.answerDraft?.answer ?? "";
      starBaseline.current = JSON.stringify(
        value.starDraft ? starValue(value.starDraft) : emptyStarInput(),
      );
      if (overwrite) {
        if (value.answerDraft) restoreAnswer(value.answerDraft.answer);
        setApplicationId(value.answerDraft?.applicationId ?? null);
      }
      if (overwriteStar && value.starDraft) {
        form.reset(starValue(value.starDraft));
        setGenerationCategory(value.starDraft.generationTargetCategory);
      }
    },
    [form, restoreAnswer],
  );
  useEffect(() => {
    if (!drafts.data || initialized.current || !isActive()) return;
    initialized.current = true;
    const liveCache =
      localCache &&
      (!localCache.serverDraftId ||
        localCache.serverDraftId === drafts.data.answerDraft?.id);
    const localText = latest.current.dirty
      ? latest.current.answer
      : liveCache
        ? localCache.draft
        : latest.current.answer;
    const answerConflict =
      (latest.current.dirty || liveCache) &&
      !!drafts.data.answerDraft &&
      localText !== drafts.data.answerDraft.answer;
    const starConflict =
      form.formState.isDirty &&
      !!drafts.data.starDraft &&
      JSON.stringify(latest.current.input) !==
        JSON.stringify(starValue(drafts.data.starDraft));
    const conflict = answerConflict || starConflict;
    if (!latest.current.dirty && liveCache && answerConflict)
      restoreAnswer(localText);
    hydrate(
      drafts.data,
      !latest.current.dirty && !answerConflict,
      !form.formState.isDirty,
    );
    if (conflict) {
      setStatus("競合");
      setError("入力中の内容と保存版が異なります。入力は保持しています。");
    } else setStatus(pending ? "保存失敗" : "保存済");
  }, [
    drafts.data,
    form,
    hydrate,
    isActive,
    localCache,
    pending,
    restoreAnswer,
  ]);
  useEffect(() => {
    if (
      !preferences.data ||
      !initialized.current ||
      starMeta.current ||
      form.formState.isDirty ||
      !isActive()
    )
      return;
    const value = {
      ...emptyStarInput(),
      targetCategory: preferences.data.category?.targetCategory ?? null,
      industry: preferences.data.details?.industry ?? "",
      company: preferences.data.details?.company ?? "",
    };
    starBaseline.current = JSON.stringify(value);
    form.reset(value);
  }, [preferences.data, drafts.data, form, isActive]);

  const run = async <T>(
    path: string,
    body: unknown,
    schema: z.ZodType<T>,
    method: "POST" | "PUT" = "POST",
  ): Promise<T> => {
    assertActive();
    if (!active.current) throw new ApiError("DRAFT_CLOSED", 409);
    if (locked.current || pending)
      throw new Error("未確定の保存を再確認してください。");
    locked.current = true;
    setStatus("保存中");
    setError(null);
    const operation: StarOperation = {
      version: 1,
      key: crypto.randomUUID(),
      path,
      method,
      body,
      contextId,
      editGeneration: editGeneration.current,
    };
    storage.save(operationKey, operation);
    setPending(operation);
    try {
      const result = schema.parse(await mutation.mutateAsync(operation));
      assertActive();
      storage.removeSaved(operationKey);
      setPending(null);
      setStatus("保存済");
      return result;
    } catch (cause) {
      if (isActive()) {
        setStatus(
          cause instanceof ApiError && cause.status === 409
            ? "競合"
            : "保存失敗",
        );
        setError(
          cause instanceof Error ? cause.message : "保存できませんでした。",
        );
        if (!uncertain(cause)) {
          storage.removeSaved(operationKey);
          setPending(null);
        }
      }
      throw cause;
    } finally {
      locked.current = false;
    }
  };
  const saveAnswer = async () => {
    if (!contextId) throw new Error("回答文脈を確認しています。");
    const snapshot = latest.current.answer;
    const body = { answer: snapshot, applicationId };
    const previous = answerMeta.current;
    const result = await run(
      previous
        ? `/answer-drafts/${previous.id}`
        : `/answer-contexts/${contextId}/answer-drafts`,
      previous ? { ...body, expectedVersion: previous.version } : body,
      starReceiptSchema,
      previous ? "PUT" : "POST",
    );
    answerMeta.current = result;
    setAnswerCache({ id: result.id, expiresAt: result.expiresAt! });
    answerBaseline.current = snapshot;
    return result;
  };
  const saveStar = async () => {
    if (!contextId) throw new Error("回答文脈を確認しています。");
    const parsed = starInputSchema.safeParse(latest.current.input);
    if (!parsed.success) {
      setStatus("保存失敗");
      setError(
        "入力の文字数・回答案を確認してください。入力は保持しています。",
      );
      throw new Error("StarInputInvalid");
    }
    const snapshot = parsed.data,
      previous = starMeta.current;
    const result = await run(
      previous
        ? `/star-drafts/${previous.id}`
        : `/answer-contexts/${contextId}/star-drafts`,
      previous ? { ...snapshot, expectedVersion: previous.version } : snapshot,
      starReceiptSchema,
      previous ? "PUT" : "POST",
    );
    starMeta.current = result;
    starBaseline.current = JSON.stringify(snapshot);
    if (snapshot.generationId === generationId && snapshot.candidates.length === 3)
      storage.removeSaved(generationKey);
    return result;
  };
  useEffect(() => {
    if (
      !enabled ||
      !contextId ||
      !initialized.current ||
      pending ||
      status === "競合" ||
      status === "保存失敗"
    )
      return;
    const answerChanged = dirty && answer !== answerBaseline.current;
    const starChanged =
      form.formState.isDirty && inputJson !== starBaseline.current;
    if (!answerChanged && !starChanged) return;
    setStatus("未保存");
    const timer = setTimeout(() => {
      if (locked.current || !isActive() || !active.current) return;
      void (answerChanged ? saveAnswer() : saveStar()).catch(() => undefined);
    }, 1000);
    return () => clearTimeout(timer);
    // Save snapshots are read from refs immediately before the serialized request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    answer,
    inputJson,
    dirty,
    enabled,
    contextId,
    pending,
    status,
    form.formState.isDirty,
    isActive,
  ]);
  const adopt = useCallback(() => {
    const result = generation.data?.result;
    if (!result || result.status !== "ready" || !generationId || !isActive())
      return;
    form.setValue("candidates", result.candidates, {
      shouldDirty: true,
      shouldValidate: true,
    });
    form.setValue("generationId", generationId, { shouldDirty: true });
    form.setValue("selectedCandidateId", null, { shouldDirty: true });
    setGenerationCategory(generation.data!.generationTargetCategory);
    setResultWaiting(false);
  }, [generation.data, generationId, form, isActive]);
  useEffect(() => {
    if (
      !generation.data ||
      !generationId ||
      handledGeneration.current === generationId ||
      ![
        "SUCCEEDED",
        "NEEDS_INFORMATION",
        "CANCELLED",
        "FAILED_BEFORE_START",
        "FAILED_AFTER_START",
        "OUTCOME_UNKNOWN",
      ].includes(generation.data.status) ||
      !isActive()
    )
      return;
    handledGeneration.current = generationId;
    void quota.refetch();
    if (generation.data.result?.status === "ready") {
      if (generatedFrom.current === JSON.stringify(latest.current.input))
        adopt();
      else setResultWaiting(true);
    } else if (generation.data.result)
      setError(generation.data.result.missingInformation.join(" "));
    else
      setError(`生成状態: ${generation.data.status}。自動再生成はしません。`);
  }, [generation.data, generationId, adopt, isActive, quota]);

  const generate = async () => {
    const sourceInput = JSON.stringify(latest.current.input);
    try {
      const row =
        starMeta.current &&
        JSON.stringify(latest.current.input) === starBaseline.current
          ? starMeta.current
          : await saveStar();
      generatedFrom.current = sourceInput;
      const result = await run(
        "/star-assist/generations",
        { starDraftId: row.id, expectedVersion: row.version },
        generationReceiptSchema,
      );
      rememberGeneration(result.generationId);
      void quota.refetch();
    } catch {
      /* run preserves input and exposes its error. */
    }
  };
  const apply = async () => {
    try {
      const snapshot = latest.current.input,
        selected = snapshot.candidates.find(
          (c) => c.id === snapshot.selectedCandidateId,
        );
      if (!selected) return;
      const epoch = editGeneration.current;
      const star =
        starMeta.current && JSON.stringify(snapshot) === starBaseline.current
          ? starMeta.current
          : await saveStar();
      const normal = answerMeta.current ?? (await saveAnswer());
      const result = await run(
        `/star-drafts/${star.id}/applications`,
        {
          expectedVersion: star.version,
          candidateId: selected.id,
          answerDraftId: normal.id,
          expectedAnswerVersion: normal.version,
        },
        applyReceiptSchema,
      );
      answerMeta.current = starReceiptSchema.parse({
        id: result.id,
        version: result.version,
        updatedAt: result.updatedAt,
        expiresAt: result.expiresAt,
      });
      setAnswerCache({ id: result.id, expiresAt: result.expiresAt });
      answerBaseline.current = selected.text;
      if (editGeneration.current === epoch && isActive() && active.current) {
        restoreAnswer(selected.text);
        setApplicationId(result.applicationId);
      } else {
        setStatus("未保存");
        setApplicationId(null);
        setError("編集中の本文を保持しました。反映結果で上書きしていません。");
      }
    } catch {
      /* Fixed visible error; applicant input remains. */
    }
  };
  const loadSaved = async () => {
    if (!contextId) return;
    try {
      const value = await getDrafts(contextId);
      assertActive();
      hydrate(value, true);
      setStatus("保存済");
      setError(null);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "保存版を取得できません。",
      );
    }
  };
  const inspectSaved = async () => {
    if (!contextId) return;
    try {
      const value = await getDrafts(contextId);
      assertActive();
      setSavedPreview(value.answerDraft?.answer ?? "（有効な通常下書きなし）");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "保存版を取得できません。",
      );
    }
  };
  const saveMine = async () => {
    if (!contextId) return;
    try {
      const value = await getDrafts(contextId);
      assertActive();
      hydrate(value, false);
      await saveAnswer();
      await saveStar();
      setStatus("保存済");
      setError(null);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "保存版を取得できません。",
      );
    }
  };
  const recover = async () => {
    if (!pending || locked.current) return;
    locked.current = true;
    try {
      let value: unknown;
      try {
        const found = await getStarRequest(pending.key);
        if (
          found.method !== pending.method ||
          found.path !== pending.path ||
          found.requestHash !==
            sha256(canonical([pending.method, pending.path, pending.body]))
        )
          throw new Error("保存要求が一致しません。");
        value = found.receipt;
      } catch (cause) {
        if (!(cause instanceof ApiError && cause.status === 404)) throw cause;
        value = await mutation.mutateAsync(pending);
      }
      responseSchema(pending).parse(value);
      assertActive();
      storage.removeSaved(operationKey);
      setPending(null);
      if (pending.path === "/star-assist/generations") {
        const accepted = generationReceiptSchema.parse(value);
        rememberGeneration(accepted.generationId);
        generatedFrom.current = null;
      }
      if (contextId) {
        const current = await getDrafts(contextId);
        assertActive();
        hydrate(current, false);
      }
      setStatus("競合");
      setError(
        "要求の結果を確認しました。保存版と入力中の内容を確認してください。",
      );
    } catch (cause) {
      if (isActive()) {
        setStatus("保存失敗");
        setError(
          cause instanceof Error ? cause.message : "再確認できませんでした。",
        );
      }
    } finally {
      locked.current = false;
    }
  };
  const savePreferences = async (categoryOnly = false) => {
    const p = preferences.data,
      v = latest.current.input;
    try {
      await run(
        "/star-assist/preferences",
        {
          ...(categoryOnly && v.targetCategory
            ? {
                category: {
                  expectedVersion: p?.category?.version ?? 0,
                  expectedGeneration: p?.category?.generationId ?? null,
                  targetCategory: v.targetCategory,
                },
              }
            : {}),
          ...(!categoryOnly
            ? {
                details: {
                  expectedVersion: p?.details?.version ?? 0,
                  expectedGeneration: p?.details?.generationId ?? null,
                  industry: v.industry,
                  company: v.company,
                },
              }
            : {}),
        },
        preferencesReceiptSchema,
        "PUT",
      );
      await preferences.refetch();
    } catch {
      /* Input retained. */
    }
  };
  const clearApplication = () => setApplicationId(null);
  const selectCategory = (value: StarInput["targetCategory"]) => {
    form.setValue("targetCategory", value, {
      shouldDirty: true,
      shouldValidate: true,
    });
    latest.current = {
      ...latest.current,
      input: { ...latest.current.input, targetCategory: value },
    };
    if (value) void savePreferences(true);
  };
  const [migrationWarning] = useState(() => {
    try {
      return typeof window !== "undefined" &&
        window.sessionStorage.getItem("pocket:mock:v4:unmerged") !== null
        ? "未統合の旧体験版データがあります。元データは保持しています。"
        : null;
    } catch {
      return null;
    }
  });
  return {
    form,
    input,
    contextId,
    status,
    error: error ?? context.error?.message ?? drafts.error?.message ?? null,
    applicationId,
    answerCache,
    quota: quota.data,
    loading: context.isPending || drafts.isPending,
    busy: mutation.isPending,
    generating:
      !!generationId &&
      (!generation.data ||
        ["QUEUED", "PREPARED", "STARTED"].includes(generation.data.status)),
    generationCategory,
    resultWaiting,
    pending: !!pending,
    generate,
    apply,
    adopt,
    loadSaved,
    saveMine,
    inspectSaved,
    savedPreview,
    recover,
    savePreferences,
    selectCategory,
    clearApplication,
    migrationWarning,
    discardStar: async () => {
      try {
        if (starMeta.current)
          await run(
            `/star-drafts/${starMeta.current.id}/discard`,
            { expectedVersion: starMeta.current.version },
            starReceiptSchema,
          );
        starMeta.current = null;
        setGenerationId(null);
        setGenerationCategory(null);
        setResultWaiting(false);
        const value = emptyStarInput();
        starBaseline.current = JSON.stringify(value);
        form.reset(value);
        setStatus("保存済");
        void quota.refetch();
      } catch {
        /* run exposes the failure and preserves edits. */
      }
    },
    refresh: () => {
      void context.refetch();
      void drafts.refetch();
    },
    discard: async () => {
      try {
        if (answerMeta.current)
          await run(
            `/answer-drafts/${answerMeta.current.id}/discard`,
            { expectedVersion: answerMeta.current.version },
            starReceiptSchema,
          );
        answerMeta.current = null;
        clearApplication();
      } catch {
        /* Visible error. */
      }
    },
  };
}
export type StarWorkspace = ReturnType<typeof useStarWorkspace>;
