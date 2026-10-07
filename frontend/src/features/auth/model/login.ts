/** @file login.ts @description Typed view models and validation for login. */
import { z } from "zod";
export const loginSchema = z.object({
  email: z.email("メールアドレスを確認してください。"),
  code: z.string(),
});
export function safeReturn(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//"))
    return "/practice/";
  try {
    const url = new URL(value, "https://app.invalid");
    return url.origin === "https://app.invalid" &&
      [
        "/practice/",
        "/practice/session/",
        "/result/",
        "/admin/questions/",
      ].includes(url.pathname)
      ? url.pathname + url.search
      : "/practice/";
  } catch {
    return "/practice/";
  }
}

export type LoginInput = z.infer<typeof loginSchema>;
export type LoginView = {
  stage: "email" | "code";
  cooldown: number;
  pending: boolean;
  error?: string;
};
