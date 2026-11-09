/** @file useEmailOtpLogin.ts @description State and side-effect controller for useEmailOtpLogin. */
"use client";
import { type FormEvent, useEffect, useReducer, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { auth } from "@/lib/auth/session";
import {
  clearRememberedEmail,
  getRememberedEmail,
  saveRememberedEmail,
} from "@/lib/auth/rememberedEmail";
import {
  loginSchema,
  safeReturn,
  type LoginInput,
  type LoginView,
} from "../model/login";
export function useEmailOtpLogin() {
  const router = useRouter();
  const params = useSearchParams();
  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", code: "" },
  });
  const [stage, setStage] = useReducer(
    (_old: "email" | "code", next: "email" | "code") => next,
    "email",
  );
  const session = useRef("");
  const sending = useRef(false);
  const restorationAttempted = useRef(false);
  const emailEdited = useRef(false);
  const [hasRememberedEmail, setHasRememberedEmail] = useState(false);
  const [rememberedEmailError, setRememberedEmailError] = useState<string>();
  const [cooldown, setCooldown] = useState(0);
  const begin = useMutation({
    mutationFn: (email: string) => auth.begin(email),
  });
  const complete = useMutation({
    mutationFn: ({ email, code }: { email: string; code: string }) =>
      auth.complete(email, session.current, code),
  });
  useEffect(() => {
    if (restorationAttempted.current) return;
    restorationAttempted.current = true;
    const saved = getRememberedEmail();
    if (!saved) return;
    setHasRememberedEmail(true);
    if (
      stage !== "email" ||
      sending.current ||
      emailEdited.current ||
      form.getValues("email") !== "" ||
      form.formState.isDirty ||
      form.getFieldState("email").isTouched
    ) return;
    // Treat the restored email as the pristine default, not a user edit.
    form.reset({ email: saved, code: "" });
  }, [form, stage]);
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);
  async function send() {
    if (sending.current || (stage === "code" && cooldown > 0)) return;
    sending.current = true;
    if (!(await form.trigger("email"))) {
      sending.current = false;
      return;
    }
    try {
      session.current = await begin.mutateAsync(form.getValues("email"));
      form.setValue("code", "");
      setStage("code");
      setCooldown(60);
    } catch {
      /* Safe message below. */
    } finally {
      sending.current = false;
    }
  }
  const onValid = async (values: LoginInput) => {
    if (stage === "email") {
      await send();
      return;
    }
    if (sending.current) return;
    if (![6, 8].includes(values.code.length) || /[^0-9]/.test(values.code)) {
      form.setError("code", {
        message: "6桁または8桁の半角数字を入力してください。",
      });
      return;
    }
    sending.current = true;
    try {
      await complete.mutateAsync(values);
      // This convenience write must never turn a successful OTP login into a failure.
      saveRememberedEmail(values.email);
      router.replace(safeReturn(params.get("returnTo")));
    } catch {
      /* Never display SDK exception payloads. */
    } finally {
      sending.current = false;
    }
  };
  const pending = begin.isPending || complete.isPending;

  return {
    form,
    view: {
      stage,
      cooldown,
      pending,
      hasRememberedEmail,
      rememberedEmailError,
      error: begin.error
        ? "コードを送信できませんでした。接続設定・登録状況を確認して再試行してください。"
        : complete.error
          ? "コードまたは有効期限を確認してください。必要なら再送してください。"
          : undefined,
    } satisfies LoginView,
    actions: {
      submit: (event?: FormEvent<HTMLFormElement>) =>
        form.handleSubmit(onValid)(event),
      resend: send,
      emailEdited: () => {
        emailEdited.current = true;
        setRememberedEmailError(undefined);
      },
      clearSavedEmail: () => {
        if (sending.current || pending || stage !== "email" || !hasRememberedEmail) return;
        if (!clearRememberedEmail()) {
          setRememberedEmailError("保存したメールアドレスを削除できませんでした。");
          return;
        }
        setHasRememberedEmail(false);
        setRememberedEmailError(undefined);
        form.reset({ email: "", code: "" });
      },
      changeEmail: () => {
        if (sending.current) return;
        session.current = "";
        setStage("email");
        form.setValue("code", "");
        form.clearErrors("code");
        begin.reset();
        complete.reset();
      },
    },
  };
}
