/** @file LoginPage.tsx @description Presentation and composition for LoginPage. */
"use client";
import { useEmailOtpLogin } from "../../hooks/useEmailOtpLogin";
import { LoginTemplate } from "../templates/LoginTemplate";
export { safeReturn } from "../../model/login";
export function LoginPage() {
  const { form, view, actions } = useEmailOtpLogin();
  return (
    <LoginTemplate
      control={form.control}
      errors={form.formState.errors}
      view={view}
      onSubmit={actions.submit}
      onResend={() => void actions.resend()}
      onChangeEmail={actions.changeEmail}
    />
  );
}
