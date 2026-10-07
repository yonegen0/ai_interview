/** @file LoginTemplate.tsx @description Presentation and composition for LoginTemplate. */
"use client";
import { Panel } from "@/components/atoms/Panel";
import { Header } from "@/components/molecules/Header";
import {
  EmailOtpForm,
  type EmailOtpFormProps,
} from "../organisms/EmailOtpForm";
export const LoginTemplate = (props: EmailOtpFormProps) => (
  <Panel>
    <Header
      title="ログイン"
      description="登録済みのメールアドレスへ確認コードを送ります。"
    />
    <EmailOtpForm {...props} />
  </Panel>
);
