/** @file auth-restoration.test.ts @description Session restore and expired-token safe-guard regression. */
import { afterEach, expect, it, vi } from "vitest";
import type { IdentityAdapter } from "@/lib/auth/cognito";

function configure() {
  vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "false");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_REGION", "ap-northeast-1");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_CLIENT_ID", "synthetic-client");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_USER_POOL_ID", "ap-northeast-1_synthetic");
}
function jwt(sub = "user") {
  return `header.${btoa(JSON.stringify({
    sub, client_id: "synthetic-client", token_use: "access",
    iss: "https://cognito-idp.ap-northeast-1.amazonaws.com/ap-northeast-1_synthetic",
    "cognito:groups": ["USER"],
  }))}.signature`;
}
function saved() {
  sessionStorage.setItem("pocket:auth:synthetic-client", JSON.stringify({
    access: jwt(), refresh: "synthetic-refresh",
    expiresAt: Date.now() + 300_000, sub: "user", groups: ["USER"],
  }));
}
afterEach(() => {
  vi.useRealTimers();
  sessionStorage.clear();
  vi.unstubAllEnvs();
});
it("does not reveal restored identity until the refresh succeeds", async () => {
  configure();
  saved();
  vi.resetModules();
  const { auth, setIdentityAdapterForTests } = await import("@/lib/auth/session");
  let finish: ((value: Awaited<ReturnType<IdentityAdapter["refresh"]>>) => void) | undefined;
  const adapter: IdentityAdapter = {
    begin: vi.fn(), complete: vi.fn(),
    refresh: vi.fn((_token: string) => new Promise<Awaited<ReturnType<IdentityAdapter["refresh"]>>>((resolve) => { finish = resolve; })),
    revoke: vi.fn(async () => undefined),
  };
  setIdentityAdapterForTests(adapter);
  const pending = auth.initialize();
  for (let i = 0; i < 5 && !finish; i++) await Promise.resolve();
  expect(finish).toBeTypeOf("function");
  expect(auth.snapshot()).toMatchObject({ phase: "refreshing", sub: null });
  finish!({ AccessToken: jwt(), ExpiresIn: 900 });
  await pending;
  expect(auth.snapshot()).toMatchObject({ phase: "authenticated", sub: "user", groups: ["USER"] });
  await auth.logout();
});
it("preserves the refresh credential but protects cached identity during restore outage", async () => {
  configure();
  saved();
  vi.resetModules();
  const { auth, setIdentityAdapterForTests, AuthUnavailableError } = await import("@/lib/auth/session");
  const adapter: IdentityAdapter = {
    begin: vi.fn(), complete: vi.fn(),
    refresh: vi.fn(async () => { throw new Error("network disconnected"); }),
    revoke: vi.fn(async () => undefined),
  };
  setIdentityAdapterForTests(adapter);
  await auth.initialize();
  expect(auth.snapshot()).toMatchObject({ phase: "temporarily_unavailable", sub: null });
  expect(sessionStorage.getItem("pocket:auth:synthetic-client")).toContain("synthetic-refresh");
  await expect(auth.access()).rejects.toBeInstanceOf(AuthUnavailableError);
  await auth.logout();
});

it.each([16, 60, 180])("renews without OTP after a tab resumes from %i minutes", async minutes => {
  configure();
  saved();
  vi.resetModules();
  const { auth, setIdentityAdapterForTests } = await import("@/lib/auth/session");
  const adapter: IdentityAdapter = {
    begin: vi.fn(), complete: vi.fn(),
    refresh: vi.fn(async () => ({ AccessToken: jwt(), ExpiresIn: 900 })),
    revoke: vi.fn(async () => undefined),
  };
  setIdentityAdapterForTests(adapter);
  await auth.initialize();
  expect(adapter.refresh).toHaveBeenCalledTimes(1);
  vi.useFakeTimers();
  vi.setSystemTime(Date.now() + minutes * 60_000);
  window.dispatchEvent(new Event("focus"));
  document.dispatchEvent(new Event("visibilitychange"));
  for (let i = 0; i < 12; i++) await Promise.resolve();
  expect(adapter.refresh).toHaveBeenCalledTimes(2);
  expect(auth.snapshot()).toMatchObject({ phase: "authenticated", sub: "user" });
  await auth.logout();
  vi.useRealTimers();
});
