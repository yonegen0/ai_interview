/** @file presentation.tsx @description 通信を使わずフォームの接続を再現する表示Story用Harness。 */
import { useEffect } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { fn } from "storybook/test";
import { zodResolver } from "@hookform/resolvers/zod";
import { bankSaveSchema, type BankSave } from "@/lib/api/schemas";
import { QuestionEditorCard } from "@/features/admin/components/molecules/QuestionEditorCard";
import { QuestionEditorList } from "@/features/admin/components/organisms/QuestionEditorList";
import { QuestionManagementTemplate } from "@/features/admin/components/templates/QuestionManagementTemplate";
import {
  changeSummary,
  type Stage,
  type ManagementActions,
} from "@/features/admin/model/editor";
import { EmailOtpForm } from "@/features/auth/components/organisms/EmailOtpForm";
import { LoginTemplate } from "@/features/auth/components/templates/LoginTemplate";
import {
  loginSchema,
  type LoginInput,
  type LoginView,
} from "@/features/auth/model/login";
import { AnswerSubmission } from "@/features/interview/components/organisms/AnswerSubmission";
import { PracticeForm } from "@/features/interview/components/templates/PracticeForm";
import type { Phase } from "@/features/interview/model/machine";
import { createSessionFixture } from "../fixtures";
import { createBankFixture, createDraftFixture } from "../fixtures/refactor";
export type AdminPresentationProps = {
  kind?: "card" | "list" | "template";
  count?: number;
  text?: string;
  stage?: Stage;
  disabled?: boolean;
  last?: boolean;
  inputError?: boolean;
  preview?: boolean;
  changed?: boolean;
};
export function AdminPresentation({
  kind = "card",
  count = 15,
  text,
  stage = "editable",
  disabled = false,
  last = false,
  inputError = false,
  preview = false,
  changed = true,
}: AdminPresentationProps) {
  const draft = createDraftFixture(count, text);
  const baseline = createBankFixture(Math.max(1, count));
  const form = useForm<BankSave>({
    resolver: zodResolver(bankSaveSchema),
    defaultValues: draft,
    mode: "onChange",
  });
  const { fields, move, remove, append } = useFieldArray({
    control: form.control,
    name: "questions",
    keyName: "fieldKey",
  });
  useWatch({ control: form.control });
  useEffect(() => {
    form.reset(createDraftFixture(count, text));
  }, [count, text, form]);
  useEffect(() => {
    if (inputError)
      form.setError("questions.0.question", {
        message: "質問本文を確認してください。",
      });
  }, [inputError, count, text, form]);
  const editor = {
    control: form.control,
    fields,
    errors: form.formState.errors,
  };
  const onMove = (index: number, direction: -1 | 1) =>
    move(index, index + direction);
  if (kind === "card") {
    const index = last ? Math.max(0, fields.length - 1) : 0;
    return (
      <QuestionEditorCard
        {...editor}
        fieldKey={fields[index].fieldKey}
        index={index}
        first={index === 0}
        last={index === fields.length - 1}
        disabled={disabled}
        onMove={(direction) => onMove(index, direction)}
        onRemove={() => remove(index)}
      />
    );
  }
  if (kind === "list")
    return (
      <QuestionEditorList
        {...editor}
        disabled={disabled}
        onMove={onMove}
        onRemove={remove}
      />
    );
  const actions: ManagementActions = {
    confirm: form.handleSubmit(fn()),
    publish: fn(async () => {}),
    back: fn(),
    cancel: () => form.reset(draft),
    togglePreview: fn(),
    refresh: fn(),
    fetchLatest: fn(async () => {}),
    adoptLatest: fn(),
    appendQuestion: () => append(createBankFixture(1).questions[0]),
    removeQuestion: remove,
    moveQuestion: onMove,
  };
  return (
    <QuestionManagementTemplate
      editor={editor}
      actions={actions}
      view={{
        initialized: true,
        loading: false,
        stage,
        error: null,
        message: "",
        changed,
        disabled: disabled || !["editable", "success"].includes(stage),
        canConfirm: changed && stage === "editable",
        questions: form.getValues("questions"),
        comparison: stage === "conflict" ? { ...baseline, version: 1 } : null,
        previousDraft: null,
        preview,
        summary: changeSummary(draft.questions, baseline.questions),
      }}
    />
  );
}
export type LoginPresentationProps = {
  template?: boolean;
  stage?: LoginView["stage"];
  pending?: boolean;
  cooldown?: number;
  error?: string;
  invalid?: "email" | "code";
};
export function LoginPresentation({
  template = false,
  stage = "email",
  pending = false,
  cooldown = 0,
  error,
  invalid,
}: LoginPresentationProps) {
  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "user@example.invalid", code: "" },
  });
  useEffect(() => {
    form.clearErrors();
    if (invalid)
      form.setError(invalid, {
        message:
          invalid === "email"
            ? "メールアドレスを確認してください。"
            : "6桁のコードを入力してください。",
      });
  }, [invalid, form]);
  const props = {
    control: form.control,
    errors: form.formState.errors,
    view: { stage, pending, cooldown, error },
    onSubmit: form.handleSubmit(fn()),
    onResend: fn(),
    onChangeEmail: fn(),
  };
  return template ? <LoginTemplate {...props} /> : <EmailOtpForm {...props} />;
}
export type AnswerPresentationProps = {
  template?: boolean;
  text?: string;
  phase?: Phase;
  inputError?: string;
  confirm?: boolean;
  legacy?: boolean;
};
export function AnswerPresentation({
  template = false,
  text = "",
  phase = "answering",
  inputError,
  confirm = false,
  legacy = false,
}: AnswerPresentationProps) {
  const form = useForm<{ answer: string }>({ defaultValues: { answer: text } });
  useEffect(() => {
    form.reset({ answer: text });
  }, [text, form]);
  const answer = useWatch({ control: form.control, name: "answer" }) ?? "";
  const bindings = {
    field: form.register("answer"),
    count: answer.length,
    phase,
    valid: !!answer.trim() && answer.length <= 500 && !inputError,
    inputError,
    error: null,
    onSubmit: form.handleSubmit(fn()),
    onReconfirm: fn(),
  };
  if (!template) return <AnswerSubmission {...bindings} />;
  return (
    <PracticeForm
      form={bindings}
      view={{
        session: createSessionFixture(
          legacy ? {} : { mode: "full", totalQuestions: 15, hasNext: true },
        ),
        phase,
        confirm,
        elapsed: 10,
        paused: false,
        evaluationError: null,
      }}
      actions={{
        retry: fn(),
        refreshEvaluation: fn(),
        requestExit: fn(),
        closeExit: fn(),
        exit: fn(),
      }}
    />
  );
}
