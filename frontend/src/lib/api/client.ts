/** @file client.ts @description 検証・Timeout・Abortを統一したAPI Client */
import { z } from "zod";
import { errorSchema } from "./schemas";

const messages: Record<string, string> = {
  VALIDATION_ERROR: "入力内容を確認してください。",
  UNAUTHORIZED: "この操作には認証が必要です。",
  SESSION_NOT_FOUND: "練習が見つかりません。",
  ATTEMPT_NOT_FOUND: "回答が見つかりません。",
  SESSION_STATE_CONFLICT:
    "練習が更新されています。現在の練習を確認してください。",
  IDEMPOTENCY_CONFLICT:
    "送信内容が一致しません。現在の練習を確認してください。",
  EVALUATION_NOT_COMPLETED: "評価はまだ完了していません。",
  EVALUATION_FAILED: "評価の作成に失敗しました。",
  INTERNAL_SERVER_ERROR: "サービスで問題が発生しました。",
  NETWORK_ERROR: "通信できませんでした。接続を確認してください。",
  TIMEOUT: "通信に時間がかかっています。結果を再確認してください。",
  INVALID_RESPONSE: "応答を確認できませんでした。",
  ABORTED: "通信を中断しました。",
};
export class ApiError extends Error {
  constructor(
    public code: string,
    public status = 0,
  ) {
    super(messages[code] ?? "処理を完了できませんでした。");
    this.name = "ApiError";
  }
}
export const uncertain = (error: unknown) =>
  !(error instanceof ApiError) ||
  error.status >= 500 ||
  ["NETWORK_ERROR", "TIMEOUT", "INVALID_RESPONSE", "ABORTED"].includes(
    error.code,
  );
export const retryGet = (count: number, error: Error) =>
  count < 1 &&
  error instanceof ApiError &&
  (error.code === "NETWORK_ERROR" || error.status >= 500);
export const apiBase = () =>
  (process.env.NEXT_PUBLIC_API_BASE_URL || "/api").replace(/\/$/, "");

/** 外部応答を検証して型付きデータとして返す */
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: {
    method?: string;
    body?: unknown;
    key?: string;
    signal?: AbortSignal;
    timeout?: number;
  } = {},
): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) abort();
  const timer = setTimeout(() => {
    timedOut = true;
    abort();
  }, options.timeout ?? 15000);
  try {
    const response = await fetch(`${apiBase()}${path}`, {
      method: options.method ?? "GET",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.key ? { "Idempotency-Key": options.key } : {}),
      },
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw new ApiError("INVALID_RESPONSE", response.status);
    }
    if (!response.ok) {
      const parsed = errorSchema.safeParse(data);
      throw new ApiError(
        parsed.success ? parsed.data.code : "INVALID_RESPONSE",
        response.status,
      );
    }
    const parsed = schema.safeParse(data);
    if (!parsed.success)
      throw new ApiError("INVALID_RESPONSE", response.status);
    return parsed.data;
  } catch (error) {
    if (timedOut) throw new ApiError("TIMEOUT");
    if (controller.signal.aborted) throw new ApiError("ABORTED");
    if (error instanceof ApiError) throw error;
    throw new ApiError("NETWORK_ERROR");
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}
