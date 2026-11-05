/** @file session.ts @description タブ内認証、復元時の本人再確認、期限更新の単一実行。 */
import type { AuthenticationResultType } from "@aws-sdk/client-cognito-identity-provider";
import type { IdentityAdapter } from "./cognito";
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
let initialized = false;
let initializeTask: Promise<void> | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let generation = 0;
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
  if (tokens && (state.phase === "temporarily_unavailable" ||
    tokens.expiresAt - Date.now() <= 30000))
    void auth.access(true).catch(() => undefined);
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
  emit({ phase: "refreshing", sub: null, groups: [] });
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
      const rejected = error instanceof InvalidAuthResponseError ||
        (await import("./cognito")).isRefreshCredentialRejected(error);
      if (rejected) {
        auth.invalidate();
        throw new AuthRequiredError("ログインし直してください。");
      }
      if (previouslyVerified && before.expiresAt > Date.now()) {
        emit({ phase: "authenticated", sub: before.sub, groups: before.groups });
      } else {
        emit({
          phase: "temporarily_unavailable",
          sub: null,
          groups: [],
          error: "通信の問題で認証を確認できません。接続が回復したら再確認します。",
        });
      }
      scheduleExpiryOnly();
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
      window.addEventListener("online", onResume);
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
    generation++;tokens=null;refreshTask=null;clearTimeout(refreshTimer);clearStored();
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
  async access(force = false): Promise<string> {
    if (mockAuth()) {
      if (state.phase === "restoring") auth.setMockActor("mock-user", ["USER"]);
      if (!state.sub) throw new AuthRequiredError("ログインしてください。");
      return `mock:${encodeURIComponent(state.sub)}:${state.groups.includes("ADMIN") ? "ADMIN" : "USER"}`;
    }
    if (!initialized) await auth.initialize();
    else if (initializeTask) await initializeTask;
    if (!tokens) throw new AuthRequiredError("ログインしてください。");
    if (state.phase === "temporarily_unavailable" && !force)
      throw new AuthUnavailableError("認証を確認できません。");
    if (!force && state.phase === "authenticated" &&
      tokens.expiresAt - Date.now() > 30000) return tokens.access;
    return renew();
  },
  async logout() {
    const previous = tokens;
    generation++;
    tokens = null;
    refreshTask = null;
    clearTimeout(refreshTimer);
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
    clearStored();
    emit({
      phase: "anonymous",
      sub: null,
      groups: [],
      error: "ログインし直してください。編集内容は保持しています。",
    });
  },
  setMockActor(sub: string, groups: string[]) {
    if (!mockAuth()) throw new Error("Mock authentication disabled");
    generation++;
    initialized = true;
    tokens = null;
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
