/** @file session.ts @description タブ内認証、復元時の本人再確認、期限更新の単一実行。 */
import type { AuthenticationResultType } from "@aws-sdk/client-cognito-identity-provider";
import type { IdentityAdapter, IdentityProfile } from "./cognito";
import { normalizeNickname } from "./nickname";
import { markStorageUnavailable } from "../storage/status";

export type AuthPhase =
  "restoring" | "anonymous" | "challenge" | "authenticated" | "refreshing" | "temporarily_unavailable";
export type AuthState = {
  phase: AuthPhase;
  sub: string | null;
  groups: string[];
  error?: string;
};
type Tokens = {
  access: string;
  refresh: string;
  expiresAt: number;
  sub: string;
  groups: string[];
};
export class AuthUnavailableError extends Error {}
export class AuthRequiredError extends Error {}
class InvalidAuthResponseError extends Error {}
const serverState: AuthState = { phase: "restoring", sub: null, groups: [] };
let state = serverState;
let tokens: Tokens | null = null;
let refreshTask: Promise<string> | null = null;
let adapter: IdentityAdapter | null = null;
const mockNicknames = new Map<string, string>();
let initialized = false;
let initializeTask: Promise<void> | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let retryTimer: ReturnType<typeof setTimeout> | undefined;
const retryDelaysMs = [2000, 5000, 15000] as const;
let retryAttempts = 0;
let retryPending = false;
let retryStopped = false;
let onlineRecoveryUsed = false;
let onlineRecoveryRequested = false;
let generation = 0;
let verifiedGeneration = -1;
const listeners = new Set<() => void>();
export const mockAuth = () => process.env.NEXT_PUBLIC_MSW_ENABLED === "true";
const clientId = () =>
  mockAuth()
    ? "mock"
    : process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID || "unconfigured";
const tokenKey = () => `pocket:auth:${clientId()}`;
const emit = (value: AuthState) => {
  state = value;
  listeners.forEach((fn) => fn());
};
const clearStored = () => {
  try {
    sessionStorage.removeItem(tokenKey());
  } catch {
    /* Memory remains available. */
  }
};
function persist() {
  try {
    if (tokens) sessionStorage.setItem(tokenKey(), JSON.stringify(tokens));
  } catch {
    markStorageUnavailable();
  }
}
function resetRetry(newSession = false) {
  clearTimeout(retryTimer);
  retryTimer = undefined;
  retryAttempts = 0;
  retryPending = false;
  retryStopped = false;
  if (newSession) {
    onlineRecoveryUsed = false;
    onlineRecoveryRequested = false;
  }
}
/** One backoff sequence per credential; visibility changes never reset its budget. */
function scheduleRetry() {
  if (!tokens || mockAuth() || retryStopped || retryTimer !== undefined) return;
  if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
  if (retryAttempts >= retryDelaysMs.length) {
    retryStopped = true;
    return;
  }
  const epoch = generation;
  const credential = tokens.refresh;
  retryTimer = setTimeout(() => {
    retryTimer = undefined;
    if (epoch !== generation || !tokens || tokens.refresh !== credential || retryStopped) return;
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
    retryAttempts++;
    void renew().catch(() => undefined);
  }, retryDelaysMs[retryAttempts]);
}
function scheduleExpiryOnly() {
  clearTimeout(refreshTimer);
  if (!tokens || mockAuth()) return;
  const current = tokens;
  const epoch = generation;
  refreshTimer = setTimeout(() => {
    if (generation !== epoch || tokens !== current) return;
    if (Date.now() >= current.expiresAt)
      emit({
        phase: "temporarily_unavailable",
        sub: null,
        groups: [],
        error: "認証を確認できません。接続が回復したら再確認します。",
      });
  }, Math.max(0, current.expiresAt - Date.now() + 20));
}
function schedule() {
  clearTimeout(refreshTimer);
  if (tokens && !mockAuth())
    refreshTimer = setTimeout(
      () => { void auth.access(true).catch(() => undefined); },
      Math.max(0, tokens.expiresAt - Date.now() - 30000),
    );
}
function onResume() {
  if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
  if (!tokens || refreshTask || retryTimer !== undefined) return;
  if (retryStopped) {
    // One additional bounded sequence after reconnection; focus alone cannot restart it.
    if (onlineRecoveryRequested && !onlineRecoveryUsed) {
      onlineRecoveryRequested = false;
      onlineRecoveryUsed = true;
      void auth.recheck().catch(() => undefined);
    }
    return;
  }
  if (retryPending) {
    scheduleRetry();
    return;
  }
  if (state.phase === "temporarily_unavailable" || tokens.expiresAt - Date.now() <= 30000)
    void auth.access(true).catch(() => undefined);
}
function onOnline() {
  if (tokens && retryStopped && !onlineRecoveryUsed) onlineRecoveryRequested = true;
  onResume();
}
async function identity() {
  if (!adapter) adapter = (await import("./cognito")).cognitoAdapter();
  return adapter;
}
function parseToken(access: string): { sub: string; groups: string[] } {
  const part = access.split(".")[1];
  if (!part) throw new InvalidAuthResponseError("認証応答を確認できませんでした。");
  const value: unknown = JSON.parse(
    atob(part.replace(/-/g, "+").replace(/_/g, "/")),
  );
  if (!value || typeof value !== "object")
    throw new InvalidAuthResponseError("認証応答を確認できませんでした。");
  const claims = value as Record<string, unknown>;
  const issuer = `https://cognito-idp.${process.env.NEXT_PUBLIC_COGNITO_REGION}.amazonaws.com/${process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID}`;
  if (
    typeof claims.sub !== "string" ||
    !claims.sub ||
    claims.token_use !== "access" ||
    claims.client_id !== clientId() ||
    claims.iss !== issuer
  )
    throw new InvalidAuthResponseError("認証応答の接続先を確認してください。");
  const groups = claims["cognito:groups"];
  return {
    sub: claims.sub,
    groups: Array.isArray(groups)
      ? groups.filter((g): g is string => typeof g === "string")
      : [],
  };
}
function accept(result: AuthenticationResultType, previous?: Tokens) {
  if (
    !result.AccessToken ||
    !(result.RefreshToken || previous?.refresh) ||
    !result.ExpiresIn ||
    result.ExpiresIn <= 0
  )
    throw new InvalidAuthResponseError("認証応答を確認できませんでした。");
  const claims = parseToken(result.AccessToken);
  if (previous && claims.sub !== previous.sub)
    throw new InvalidAuthResponseError("ログイン利用者が変わりました。");
  resetRetry(true);
  verifiedGeneration = generation;
  tokens = {
    access: result.AccessToken,
    refresh: result.RefreshToken || previous!.refresh,
    expiresAt: Date.now() + result.ExpiresIn * 1000,
    ...claims,
  };
  persist();
  emit({ phase: "authenticated", sub: tokens.sub, groups: tokens.groups });
  schedule();
}
/** Renewal is single-flight; only proven credential rejection removes saved tokens. */
function renew(): Promise<string> {
  if (!tokens) return Promise.reject(new AuthRequiredError("ログインしてください。"));
  if (refreshTask) return refreshTask;
  const before = tokens;
  const epoch = generation;
  const previouslyVerified = state.phase === "authenticated";
  emit({
    phase: "refreshing",
    sub: previouslyVerified && before.expiresAt > Date.now() ? before.sub : null,
    groups: previouslyVerified && before.expiresAt > Date.now() ? before.groups : [],
  });
  // Hide protected content when a verified token expires during a pending refresh.
  scheduleExpiryOnly();
  refreshTask = (async () => {
    try {
      const result = await (await identity()).refresh(before.refresh);
      if (epoch !== generation)
        throw new AuthRequiredError("ログイン状態が変わりました。");
      accept(result, before);
      return tokens!.access;
    } catch (error) {
      if (epoch !== generation)
        throw new AuthRequiredError("ログイン状態が変わりました。");
      const { isRefreshCredentialRejected, isTransientRefreshError } = await import("./cognito");
      if (error instanceof InvalidAuthResponseError || isRefreshCredentialRejected(error)) {
        auth.invalidate();
        throw new AuthRequiredError("ログインし直してください。");
      }
      // An unconfirmed refresh must never keep verified identity visible.
      emit({
        phase: "temporarily_unavailable",
        sub: null,
        groups: [],
        error: "通信の問題で認証を確認できません。接続を確認して再度お試しください。",
      });
      scheduleExpiryOnly();
      if (isTransientRefreshError(error)) {
        retryPending = true;
        if (retryAttempts >= retryDelaysMs.length) retryStopped = true;
        else scheduleRetry();
      } else {
        // Unknown/configuration failures retain credentials but require manual review.
        retryPending = false;
        retryStopped = true;
      }
      throw new AuthUnavailableError("認証を確認できません。");
    } finally {
      if (epoch === generation) refreshTask = null;
    }
  })();
  return refreshTask;
}
export const auth = {
  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  },
  snapshot: () => state,
  serverSnapshot: () => serverState,
  /** Changes on logout or a new login, but not on token refresh. */
  generation: () => generation,
  async initialize() {
    if (initialized) return initializeTask ?? undefined;
    initialized = true;
    if (mockAuth()) {
      let role = "USER";
      try {
        const saved = sessionStorage.getItem("pocket:mock:identity");
        if (saved) {
          const actor = JSON.parse(saved) as { sub?: unknown; groups?: unknown };
          if (
            typeof actor.sub === "string" &&
            Array.isArray(actor.groups) &&
            actor.groups.every((g) => g === "USER" || g === "ADMIN")
          ) {
            auth.setMockActor(actor.sub, actor.groups);
            return;
          }
        }
        role = sessionStorage.getItem("pocket:mock:role") || role;
      } catch {
        /* Optional fixture. */
      }
      auth.setMockActor(role === "ADMIN" ? "mock-admin" : "mock-user", [role]);
      return;
    }
    if (typeof window !== "undefined") {
      window.addEventListener("focus", onResume);
      window.addEventListener("online", onOnline);
      document.addEventListener("visibilitychange", onResume);
    }
    initializeTask = (async () => {
      let saved: string | null = null;
      try {
        saved = sessionStorage.getItem(tokenKey());
      } catch {
        markStorageUnavailable();
      }
      if (saved) {
        try {
          const candidate: unknown = JSON.parse(saved);
          if (candidate && typeof candidate === "object") {
            const t = candidate as Tokens;
            const claims = typeof t.access === "string" ? parseToken(t.access) : null;
            if (
              claims &&
              typeof t.refresh === "string" && t.refresh.length > 0 &&
              Number.isFinite(t.expiresAt) && t.expiresAt > 0 &&
              t.sub === claims.sub
            ) {
              tokens = { ...t, ...claims };
              // Never reveal saved data until Cognito confirms the refresh.
              await renew();
              return;
            }
          }
        } catch {
          if (tokens) return; // renew already classified the error and hid unverified data
        }
        if (!tokens) clearStored();
      }
      if (!tokens) emit({ phase: "anonymous", sub: null, groups: [] });
    })();
    return initializeTask;
  },
  async begin(email: string) {
    if (mockAuth()) {
      emit({ phase: "challenge", sub: null, groups: [] });
      return "mock-challenge";
    }
    const epoch=generation;
    const session = await (await identity()).begin(email);
    if(epoch!==generation)throw new Error("ログイン状態が変わりました。");
    generation++;tokens=null;refreshTask=null;clearTimeout(refreshTimer);resetRetry(true);verifiedGeneration=-1;clearStored();
    emit({ phase: "challenge", sub: null, groups: [] });
    return session;
  },
  async complete(email: string, session: string, code: string) {
    if (mockAuth()) {
      if (code !== "123456") throw new Error("コードを確認してください。");
      auth.setMockActor(
        email.startsWith("admin") ? "mock-admin" : "mock-user",
        email.startsWith("admin") ? ["ADMIN"] : ["USER"],
      );
      return;
    }
    const epoch=generation;
    const result=await (await identity()).complete(email, session, code);
    if(epoch!==generation)throw new Error("ログイン状態が変わりました。");
    accept(result);
  },
  async profile(): Promise<IdentityProfile> {
    const epoch = generation;
    const token = await auth.access();
    if (mockAuth()) return { nickname: mockNicknames.get(state.sub ?? "") ?? null, email: null };
    const getter = (await identity()).getProfile;
    if (!getter) throw new Error("プロフィール情報を取得できません。");
    const result = await getter(token);
    if (generation !== epoch) throw new AuthRequiredError();
    return result;
  },
  async updateNickname(value: string): Promise<void> {
    const nickname = normalizeNickname(value);
    const epoch = generation;
    const token = await auth.access();
    if (mockAuth()) {
      if (state.sub) {
        if (nickname) mockNicknames.set(state.sub, nickname);
        else mockNicknames.delete(state.sub);
      }
      return;
    }
    const save = (await identity()).updateNickname;
    if (!save) throw new Error("ニックネームを保存できません。");
    await save(token, nickname);
    if (generation !== epoch) throw new AuthRequiredError();
  },
  async access(force = false): Promise<string> {
    if (mockAuth()) {
      if (state.phase === "restoring") auth.setMockActor("mock-user", ["USER"]);
      if (!state.sub) throw new AuthRequiredError("ログインしてください。");
      return `mock:${encodeURIComponent(state.sub)}:${state.groups.includes("ADMIN") ? "ADMIN" : "USER"}`;
    }
    if (!initialized) await auth.initialize();
    else if (initializeTask) await initializeTask;
    if (!tokens) throw new AuthRequiredError("ログインしてください。");
    if (refreshTask) return refreshTask;
    if (retryStopped || (retryPending && retryTimer !== undefined))
      throw new AuthUnavailableError("認証を確認できません。");
    if (state.phase === "temporarily_unavailable" && !force)
      throw new AuthUnavailableError("認証を確認できません。");
    if (!force && state.phase === "authenticated" &&
      tokens.expiresAt - Date.now() > 30000) return tokens.access;
    return renew();
  },
  /** User-triggered reconfirmation starts a fresh, bounded sequence. */
  recheck(): Promise<string> {
    resetRetry();
    onlineRecoveryRequested = false;
    return auth.access(true);
  },
  async logout() {
    const previous = tokens;
    generation++;
    tokens = null;
    refreshTask = null;
    clearTimeout(refreshTimer);
    resetRetry(true);
    verifiedGeneration = -1;
    clearStored();
    emit({ phase: "anonymous", sub: null, groups: [] });
    if (mockAuth())
      try {
        sessionStorage.removeItem("pocket:mock:identity");
        sessionStorage.removeItem("pocket:mock:role");
      } catch {
        markStorageUnavailable();
      }
    if (previous && !mockAuth())
      try {
        await (await identity()).revoke(previous.refresh);
      } catch {
        /* Local logout completes regardless. */
      }
  },
  /** A backend 401 does not, by itself, prove refresh-token revocation. */
  suspend() {
    // Mock authentication has no refresh credential to reconfirm.
    if (mockAuth()) {
      auth.invalidate();
      return;
    }
    if (!tokens) return;
    emit({
      phase: "temporarily_unavailable",
      sub: null,
      groups: [],
      error: "認証を確認できません。接続を確認して再度お試しください。",
    });
    scheduleExpiryOnly();
  },
  invalidate() {
    generation++;
    tokens = null;
    refreshTask = null;
    clearTimeout(refreshTimer);
    resetRetry(true);
    verifiedGeneration = -1;
    clearStored();
    emit({
      phase: "anonymous",
      sub: null,
      groups: [],
      error: "ログインの有効期限が切れました。再度ログインしてください。",
    });
  },
  setMockActor(sub: string, groups: string[]) {
    if (!mockAuth()) throw new Error("Mock authentication disabled");
    generation++;
    initialized = true;
    tokens = null;
    clearTimeout(refreshTimer);
    resetRetry(true);
    verifiedGeneration = -1;
    emit({ phase: "authenticated", sub, groups });
    try {
      sessionStorage.setItem(
        "pocket:mock:identity",
        JSON.stringify({ sub, groups }),
      );
    } catch {
      markStorageUnavailable();
    }
  },
  /** Previously verified scope for retaining hidden UI only, never for API authorization. */
  retainedViewScope() {
    return verifiedGeneration === generation && tokens
      ? `pocket:v2:${encodeURIComponent(clientId())}:${encodeURIComponent(tokens.sub)}:`
      : null;
  },
  scope() {
    return state.sub
      ? `pocket:v2:${encodeURIComponent(clientId())}:${encodeURIComponent(state.sub)}:`
      : null;
  },
};
/** Unit-test injection avoids every external authentication request. */
export function setIdentityAdapterForTests(value: IdentityAdapter | null) {
  adapter = value;
}
