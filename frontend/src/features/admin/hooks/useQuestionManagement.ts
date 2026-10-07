/** @file useQuestionManagement.ts @description State and side-effect controller for useQuestionManagement. */
"use client";
import { useOperationScope } from "@/hooks/useOperationScope";
import { useEffect, useReducer, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getQuestionBank, saveQuestionBank } from "@/lib/api/admin";
import {
  bankSaveSchema,
  bankSaveSchemaForBaseline,
  type BankSave,
  type QuestionBank,
} from "@/lib/api/schemas";
import { ApiError, uncertain } from "@/lib/api/client";
import { useQuestionBankEditor } from "./useQuestionBankEditor";
import {
  savedBankSchema,
  storageKey,
  stageReducer,
  changeSummary,
  type ManagementView,
  type ManagementActions,
} from "../model/editor";
export function useQuestionManagement() {
  const {
    scope,
    isActive,
    assertActive,
    storage: { readSaved, save, removeSaved },
  } = useOperationScope();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: [scope, "admin-question-bank"],
    queryFn: ({ signal }) => {
      assertActive();
      return getQuestionBank(signal);
    },
    enabled: isActive(),
    refetchOnMount: "always",
  });
  const mutation = useMutation({
    mutationFn: ({ body, key }: { body: BankSave; key: string }) => {
      assertActive();
      return saveQuestionBank(body, key);
    },
  });
  const [baseline, setBaseline] = useState<QuestionBank | null>(null);
  const editor = useQuestionBankEditor(baseline?.questions ?? []);
  const { form, fields, draft } = editor;
  const [comparison, setComparison] = useState<QuestionBank | null>(null);
  const [previousDraft, setPreviousDraft] = useState<BankSave | null>(null);
  const [preview, setPreview] = useState(false);
  const [stage, transition] = useReducer(stageReducer, "editable");
  const [message, setMessage] = useState("");
  const pending = useRef<{ key: string; body: BankSave } | null>(null);
  const locked = useRef(false),
    loaded = useRef(false);
  useEffect(() => {
    if (
      !isActive() ||
      !query.data ||
      loaded.current ||
      !query.isFetchedAfterMount ||
      query.isFetching ||
      !query.isSuccess
    )
      return;
    loaded.current = true;
    const restored = readSaved(storageKey, savedBankSchema);
    if (restored) {
      setBaseline(restored.baseline);
      form.reset(restored.draft);
      pending.current = restored.pending || null;
      if (restored.pending) transition("uncertain");
      else if (restored.baseline.version !== query.data.version) {
        setComparison(query.data);
        transition("conflict");
      }
    } else {
      setBaseline(query.data);
      form.reset({
        expectedVersion: query.data.version,
        questions: query.data.questions,
      });
    }
  }, [
    query.data,
    query.isFetchedAfterMount,
    query.isFetching,
    query.isSuccess,
    form,
    readSaved,
    isActive,
  ]);
  useEffect(() => {
    if (!baseline || !isActive()) return;
    save(storageKey, {
      baseline,
      draft: form.getValues(),
      ...(pending.current ? { pending: pending.current } : {}),
    });
  }, [draft, baseline, stage, form, save, isActive]);
  const changed =
    baseline &&
    JSON.stringify(draft.questions) !== JSON.stringify(baseline.questions);
  const busy = ["saving", "uncertain", "conflict", "forbidden"].includes(stage);
  const [confirmation, setConfirmation] = useState<BankSave | null>(null);
  async function publish() {
    if (
      !isActive() ||
      locked.current ||
      (!pending.current && stage !== "confirm")
    )
      return;
    const validated = (
      pending.current
        ? bankSaveSchema
        : bankSaveSchemaForBaseline(baseline?.questions ?? [])
    ).safeParse(pending.current?.body ?? confirmation);
    if (!validated.success) {
      transition("editable");
      return;
    }
    const request = pending.current || {
      key: crypto.randomUUID(),
      body: structuredClone(validated.data),
    };
    locked.current = true;
    pending.current = request;
    transition("saving");
    if (baseline)
      save(storageKey, { baseline, draft: form.getValues(), pending: request });
    try {
      const receipt = await mutation.mutateAsync(request);
      if (!isActive()) return;
      const next = {
        version: receipt.version,
        updatedAt: receipt.updatedAt,
        questions: request.body.questions,
      };
      client.setQueryData([scope, "admin-question-bank"], next);
      pending.current = null;
      setBaseline(next);
      form.reset({
        expectedVersion: receipt.version,
        questions: next.questions,
      });
      setMessage(
        `質問一覧を保存しました（${receipt.totalQuestions}問）。次の新規練習から反映します。`,
      );
      transition("success");
      removeSaved(storageKey);
    } catch (error) {
      if (!isActive()) return;
      if (uncertain(error)) transition("uncertain");
      else {
        pending.current = null;
        if (
          error instanceof ApiError &&
          error.code === "QUESTION_BANK_CONFLICT"
        ) {
          transition("conflict");
          try {
            const latest = await getQuestionBank();
            if (isActive()) setComparison(latest);
          } catch {
            if (!isActive()) return;
            setMessage(
              "最新版を取得できませんでした。編集内容は保持しています。",
            );
          }
        } else
          transition(
            error instanceof ApiError && error.status === 403
              ? "forbidden"
              : "editable",
          );
      }
    } finally {
      locked.current = false;
    }
  }

  const questions = form.getValues("questions");
  async function fetchLatest() {
    if (!isActive()) return;
    try {
      const latest = await getQuestionBank();
      if (isActive()) setComparison(latest);
    } catch {
      if (!isActive()) return;
      setMessage("最新版を取得できませんでした。編集内容は保持しています。");
    }
  }
  const actions: ManagementActions = {
    confirm: (event) =>
      form.handleSubmit((value) => {
        if (!isActive() || busy || !changed || stage === "confirm") return;
        setConfirmation(structuredClone(value));
        transition("confirm");
      })(event),
    publish,
    back: () => {
      if (!isActive() || stage !== "confirm") return;
      setConfirmation(null);
      transition("editable");
    },
    cancel: () => {
      if (!isActive() || !baseline || busy || stage === "confirm") return;
      editor.resetEditor(baseline);
      mutation.reset();
      transition("editable");
    },
    togglePreview: () => setPreview((value) => !value),
    refresh: () => {
      if (isActive()) void query.refetch();
    },
    fetchLatest,
    adoptLatest: () => {
      if (!isActive() || !comparison || stage !== "conflict") return;
      setPreviousDraft(structuredClone(form.getValues()));
      setBaseline(comparison);
      editor.resetEditor(comparison);
      setComparison(null);
      mutation.reset();
      transition("editable");
    },
    appendQuestion: () => {
      if (isActive() && !busy && stage !== "confirm" && fields.length < 100)
        editor.appendQuestion();
    },
    removeQuestion: (index) => {
      if (isActive() && !busy && stage !== "confirm")
        editor.removeQuestion(index);
    },
    moveQuestion: (index, direction) => {
      if (isActive() && !busy && stage !== "confirm")
        editor.moveQuestion(index, direction);
    },
  };
  return {
    view: {
      initialized: !!baseline,
      loading: query.isPending || (!baseline && !query.error),
      stage,
      error: query.error || mutation.error,
      message,
      changed: !!changed,
      disabled: !baseline || busy || stage === "confirm",
      canConfirm:
        !!changed && !busy && stage !== "confirm" && form.formState.isValid,
      questions,
      comparison,
      previousDraft,
      preview,
      summary: changeSummary(
        confirmation?.questions ?? questions,
        baseline?.questions ?? [],
      ),
    } satisfies ManagementView,
    editor: { control: form.control, fields, errors: form.formState.errors },
    actions,
  };
}
