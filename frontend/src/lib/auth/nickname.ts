/** @file nickname.ts @description Cognito nickname input policy shared by both profile editors. */
export function normalizeNickname(value: unknown): string {
  if (typeof value !== "string") throw new Error("ニックネームを確認してください。");
  const normalized = value.normalize("NFC").trim();
  if (/\p{Cc}/u.test(normalized)) throw new Error("改行や制御文字は使用できません。");
  if (Array.from(normalized).length > 24) throw new Error("ニックネームは24文字以内で入力してください。");
  return normalized;
}
