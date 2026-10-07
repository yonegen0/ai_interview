/** @file useEmailOtpLogin.ts @description State and side-effect controller for useEmailOtpLogin. */
"use client";
import { type FormEvent, useEffect, useReducer, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { auth } from "@/lib/auth/session";
import {
  loginSchema,
  safeReturn,
  type LoginInput,
  type LoginView,
} from "../model/login";
export function useEmailOtpLogin() {
  const router = useRouter();
  const params = useSearchParams();
  const form = useForm({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", code: "" },
  });
  const [stage, setStage] = useReducer(
    (_old: "email" | "code", next: "email" | "code") => next,
    "email",
  );
  const session = useRef("");
  const sending = useRef(false);
  const [cooldown, setCooldown] = useState(0);
  const begin = useMutation({
    mutationFn: (email: string) => auth.begin(email),
  });
  const complete = useMutation({
    mutationFn: ({ email, code }: { email: string; code: string }) =>
      auth.complete(email, session.current, code),
  });
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
    if (!/^\d{6}$/.test(values.code)) {
      form.setError("code", { message: "6桁のコードを入力してください。" });
      return;
    }
    sending.current = true;
    try {
      await complete.mutateAsync(values);
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
