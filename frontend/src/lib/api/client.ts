/** @file client.ts @description 検証・Timeout・Abortを統一したAPI Client */
import { z } from "zod";
import { errorSchema } from "./schemas";
import { auth } from "@/lib/auth/session";

const messages: Record<string, string> = {
  DRAFT_VERSION_CONFLICT: "別のタブで保存されています。入力は保持しています。",
  DRAFT_CLOSED: "この回答段階は終了しています。現在の練習を確認してください。",
  STAR_GENERATION_IN_PROGRESS: "この回答段階の生成結果を確認してください。",
  STAR_QUOTA_EXCEEDED:
    "今月のSTAR生成上限に達しました。編集・保存は利用できます。",
  STAR_DRAFT_NOT_FOUND: "下書きを確認できません。入力は保持しています。",
  STAR_REQUEST_NOT_FOUND:
    "保存要求はまだ確認できません。同じ要求で再確認してください。",
  STAR_CONTEXT_NOT_FOUND: "回答段階を確認できません。",
  STAR_APPLICATION_NOT_FOUND: "STAR反映の記録を確認できません。",
  STAR_GENERATION_NOT_FOUND: "生成結果を確認できません。",
  VALIDATION_ERROR: "入力内容を確認してください。",
  QUESTION_BANK_CONFLICT:
    "質問が更新されています。最新版と比較して編集し直してください。",
  QUESTION_BANK_TOO_LARGE: "質問数または本文量を減らしてください。",
  REQUEST_TOO_LARGE: "保存する内容が大きすぎます。",
  CATEGORY_UNAVAILABLE:
    "このカテゴリの質問がありません。カテゴリを選び直してください。",
  SESSION_COMPLETED: "この練習は完了しています。",
  SESSION_CREATION_LIMIT:
    "今月の面接練習の新規作成上限に達しました。翌月から再び作成できます。",
  UNAUTHORIZED: "この操作には認証が必要です。",
  FORBIDDEN: "この操作を行う権限がありません。",
  RATE_LIMITED: "利用が制限されています。時間をおいて再度お試しください。",
  AI_TIMEOUT: "評価処理に時間がかかっています。結果を再確認してください。",
  AI_UPSTREAM_ERROR: "評価サービスで問題が発生しました。",
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
    applicationId?: string;
    signal?: AbortSignal;
    timeout?: number;
  } = {},
): Promise<T> {
  const owner = auth.scope();
  const generation = auth.generation();
  const assertOwner = () => {
    if (
      auth.generation() !== generation ||
      (owner !== null && auth.scope() !== owner)
    )
      throw new ApiError("UNAUTHORIZED", 401);
  };
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
    const body =
      options.body === undefined ? undefined : JSON.stringify(options.body);
    let token: string;
    try {
      token = await auth.access();
    } catch {
      throw new ApiError("UNAUTHORIZED", 401);
    }
    assertOwner();
    const send = (access: string) =>
      fetch(`${apiBase()}${path}`, {
        method: options.method ?? "GET",
        signal: controller.signal,
        redirect: "error",
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${access}`,
          "Content-Type": "application/json",
          ...(options.key ? { "Idempotency-Key": options.key } : {}),
          ...(options.applicationId
            ? { "X-Star-Application-Id": options.applicationId }
            : {}),
        },
        body,
      });
    let response = await send(token);
    assertOwner();
    if (response.status === 401) {
      try {
        token = await auth.access(true);
      } catch {
        throw new ApiError("UNAUTHORIZED", 401);
      }
      assertOwner();
      response = await send(token);
      assertOwner();
    }
    if (response.status === 401) {
      auth.invalidate();
      throw new ApiError("UNAUTHORIZED", 401);
    }
    if (response.status === 403) throw new ApiError("FORBIDDEN", 403);
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw new ApiError("INVALID_RESPONSE", response.status);
    }
    assertOwner();
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
