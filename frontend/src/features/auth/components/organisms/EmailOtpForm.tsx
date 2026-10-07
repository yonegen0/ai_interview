/** @file EmailOtpForm.tsx @description Presentation and composition for EmailOtpForm. */
"use client";
import type { FormEventHandler } from "react";
import { Controller, type Control, type FieldErrors } from "react-hook-form";
import { styled } from "@mui/material/styles";
import { Input } from "@/components/atoms/Input";
import { Text } from "@/components/atoms/Text";
import { Button } from "@/components/atoms/Button";
import { Actions } from "@/components/atoms/Actions";
import type { LoginInput, LoginView } from "../../model/login";
const Fields = styled("div")(({ theme }) => ({
  display: "grid",
  gap: theme.spacing(2),
  marginTop: theme.spacing(2),
}));
export type EmailOtpFormProps = {
  control: Control<LoginInput>;
  errors: FieldErrors<LoginInput>;
  view: LoginView;
  onSubmit: FormEventHandler<HTMLFormElement>;
  onResend: () => void;
  onChangeEmail: () => void;
};
export function EmailOtpForm({
  control,
  errors,
  view,
  onSubmit,
  onResend,
  onChangeEmail,
}: EmailOtpFormProps) {
  return (
    <form onSubmit={onSubmit} noValidate>
      <Fields>
        <Controller
          control={control}
          name="email"
          render={({ field: { ref, ...field } }) => (
            <Input
              {...field}
              inputRef={ref}
              id="login-email"
              label="メールアドレス"
              type="email"
              autoComplete="email"
              disabled={view.pending || view.stage === "code"}
              error={!!errors.email}
              helperText={errors.email?.message}
              slotProps={{ formHelperText: { role: "alert" } }}
            />
          )}
        />
        {view.stage === "code" && (
          <Controller
            control={control}
            name="code"
            render={({ field: { ref, ...field } }) => (
              <Input
                {...field}
                inputRef={ref}
                id="login-code"
                label="確認コード"
                autoComplete="one-time-code"
                slotProps={{
                  htmlInput: { inputMode: "numeric" },
                  formHelperText: { role: "alert" },
                }}
                disabled={view.pending}
                error={!!errors.code}
                helperText={errors.code?.message}
              />
            )}
          />
        )}
      </Fields>
      <Actions>
        <Button
          variant="contained"
          color="primary"
          type="submit"
          disabled={view.pending}
        >
          {view.pending
            ? "確認しています…"
            : view.stage === "email"
              ? "確認コードを送る"
              : "ログインする"}
        </Button>
        {view.stage === "code" && (
          <>
            <Button
              variant="outlined"
              color="primary"
              type="button"
              disabled={view.pending || view.cooldown > 0}
              onClick={onResend}
            >
              {view.cooldown > 0
                ? `再送まで${view.cooldown}秒`
                : "コードを再送"}
            </Button>
            <Button
              variant="outlined"
              color="primary"
              type="button"
              disabled={view.pending}
              onClick={onChangeEmail}
            >
              メールアドレスを変更
            </Button>
          </>
        )}
      </Actions>
      {view.error && <Text role="alert">{view.error}</Text>}
    </form>
  );
}
