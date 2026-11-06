/** @file auth.test.ts @description 実認証adapter境界をstubし、期限更新と本人確認を検証。 */
import { afterEach, expect, it, vi } from "vitest";
import { auth, AuthUnavailableError, setIdentityAdapterForTests } from "@/lib/auth/session";
import type { IdentityAdapter } from "@/lib/auth/cognito";
import { InvalidParameterException, NotAuthorizedException } from "@aws-sdk/client-cognito-identity-provider";
function configure() {
  vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "false");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_REGION", "ap-northeast-1");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_CLIENT_ID", "synthetic-client");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_USER_POOL_ID", "ap-northeast-1_synthetic");
}
function token(sub = "user", groups = ["ADMIN"], client = "synthetic-client") {
  return `header.${btoa(JSON.stringify({ sub, "cognito:groups": groups, client_id: client, token_use: "access", iss: "https://cognito-idp.ap-northeast-1.amazonaws.com/ap-northeast-1_synthetic" }))}.synthetic`;
}
function adapter(): IdentityAdapter {
  return {
    begin: vi.fn(async () => "session"),
    complete: vi.fn(async () => ({
      AccessToken: token(),
      RefreshToken: "synthetic-refresh",
      ExpiresIn: 300,
    })),
    refresh: vi.fn(async () => ({ AccessToken: token(), ExpiresIn: 300 })),
    revoke: vi.fn(async () => undefined),
  };
}
afterEach(async () => {
  await auth.logout();
  setIdentityAdapterForTests(null);
  sessionStorage.clear();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});
it("does not send OTP during initialization and persists access identity only", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  expect(value.begin).not.toHaveBeenCalled();
  const session = await auth.begin("user@example.invalid");
  await auth.complete("user@example.invalid", session, "123456");
  expect(auth.snapshot()).toMatchObject({
    phase: "authenticated",
    sub: "user",
    groups: ["ADMIN"],
  });
  const stored = sessionStorage.getItem("pocket:auth:synthetic-client")!;
  expect(stored).toContain("synthetic-refresh");
  expect(stored).not.toContain("123456");
  expect(stored).not.toContain("idToken");
});
it("deduplicates simultaneous refresh and preserves credentials on a transient failure", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  await auth.complete("user@example.invalid", "session", "123456");
  await Promise.all([auth.access(true), auth.access(true), auth.access(true)]);
  expect(value.refresh).toHaveBeenCalledTimes(1);
  vi.mocked(value.refresh).mockRejectedValue(
    new Error("private service payload"),
  );
  await expect(auth.access(true)).rejects.toThrow("認証を確認できません");
  expect(auth.snapshot()).toMatchObject({ phase: "temporarily_unavailable", sub: null });
  expect(sessionStorage.getItem("pocket:auth:synthetic-client")).toContain("synthetic-refresh");
});
it("invalidates a revoked refresh token using the typed Cognito error", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  await auth.complete("user@example.invalid", "s", "123456");
  vi.mocked(value.refresh).mockRejectedValueOnce(
    new NotAuthorizedException({ $metadata: { httpStatusCode: 400 }, message: "invalid refresh" }),
  );
  await expect(auth.access(true)).rejects.toThrow("ログインし直してください");
  expect(auth.snapshot().phase).toBe("anonymous");
  expect(sessionStorage.getItem("pocket:auth:synthetic-client")).toBeNull();
});
it("rejects another client and another subject during refresh", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  vi.mocked(value.complete).mockResolvedValueOnce({
    AccessToken: token("user", [], "wrong-client"),
    RefreshToken: "r",
    ExpiresIn: 300,
  });
  await expect(
    auth.complete("user@example.invalid", "s", "123456"),
  ).rejects.toThrow("接続先");
  await auth.complete("user@example.invalid", "s", "123456");
  vi.mocked(value.refresh).mockResolvedValueOnce({
    AccessToken: token("another-user"),
    ExpiresIn: 300,
  });
  await expect(auth.access(true)).rejects.toThrow();
  expect(auth.snapshot().sub).toBeNull();
});
it("completes local logout when revocation fails", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  await auth.complete("user@example.invalid", "s", "123456");
  vi.mocked(value.revoke).mockRejectedValue(new Error("private"));
  await auth.logout();
  expect(auth.snapshot().phase).toBe("anonymous");
  expect(sessionStorage.getItem("pocket:auth:synthetic-client")).toBeNull();
});

it("does not restore login from a challenge completion after logout",async()=>{
  configure();const value=adapter();setIdentityAdapterForTests(value);
  let resolve:((result:Awaited<ReturnType<IdentityAdapter["complete"]>>)=>void)|undefined;
  vi.mocked(value.complete).mockImplementation(()=>new Promise(done=>{resolve=done;}));
  const pending=auth.complete("user@example.invalid","challenge","123456");
  await Promise.resolve();await auth.logout();
  resolve!({AccessToken:token(),RefreshToken:"synthetic-refresh",ExpiresIn:300});
  await expect(pending).rejects.toThrow("ログイン状態が変わりました");expect(auth.snapshot().sub).toBeNull();
});

it("recovers after one timed-out refresh using the 2-second retry", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  await auth.complete("user@example.invalid", "s", "123456");
  vi.useFakeTimers();
  vi.mocked(value.refresh).mockRejectedValueOnce(
    Object.assign(new Error("timeout"), { name: "TimeoutError" }),
  );
  await expect(auth.access(true)).rejects.toBeInstanceOf(AuthUnavailableError);
  expect(auth.snapshot()).toMatchObject({ phase: "temporarily_unavailable", sub: null });
  expect(sessionStorage.getItem("pocket:auth:synthetic-client")).toContain("synthetic-refresh");
  await vi.advanceTimersByTimeAsync(1999);
  expect(value.refresh).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(value.refresh).toHaveBeenCalledTimes(2);
  expect(auth.snapshot()).toMatchObject({ phase: "authenticated", sub: "user" });
});

it("caps automatic retries at 2, 5 and 15 seconds and permits manual recheck", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  await auth.complete("user@example.invalid", "s", "123456");
  vi.useFakeTimers();
  vi.mocked(value.refresh).mockRejectedValue(
    Object.assign(new Error("offline"), { name: "NetworkError" }),
  );
  await expect(auth.access(true)).rejects.toBeInstanceOf(AuthUnavailableError);
  await vi.advanceTimersByTimeAsync(22_000);
  expect(value.refresh).toHaveBeenCalledTimes(4);
  expect(auth.snapshot().phase).toBe("temporarily_unavailable");
  await vi.advanceTimersByTimeAsync(30_000);
  await expect(auth.access(true)).rejects.toBeInstanceOf(AuthUnavailableError);
  expect(value.refresh).toHaveBeenCalledTimes(4);
  vi.mocked(value.refresh).mockResolvedValue({ AccessToken: token(), ExpiresIn: 300 });
  await auth.recheck();
  expect(value.refresh).toHaveBeenCalledTimes(5);
  expect(auth.snapshot()).toMatchObject({ phase: "authenticated", sub: "user" });
});

it("retains refresh credentials on InvalidParameterException without automatic retry", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  await auth.complete("user@example.invalid", "s", "123456");
  vi.useFakeTimers();
  vi.mocked(value.refresh).mockRejectedValueOnce(
    new InvalidParameterException({ $metadata: { httpStatusCode: 400 }, message: "invalid parameter" }),
  );
  await expect(auth.access(true)).rejects.toBeInstanceOf(AuthUnavailableError);
  await vi.advanceTimersByTimeAsync(30_000);
  expect(value.refresh).toHaveBeenCalledTimes(1);
  expect(sessionStorage.getItem("pocket:auth:synthetic-client")).toContain("synthetic-refresh");
  expect(auth.snapshot()).toMatchObject({ phase: "temporarily_unavailable", sub: null });
});

it("does not accept a delayed renewal after logout or user switching", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  await auth.complete("user@example.invalid", "s", "123456");
  const pendingResults: Array<(result: Awaited<ReturnType<IdentityAdapter["refresh"]>>) => void> = [];
  vi.mocked(value.refresh).mockImplementation(() => new Promise(resolve => { pendingResults.push(resolve); }));
  const pendingLogout = auth.access(true);
  for (let i = 0; i < 8 && !pendingResults.length; i++) await Promise.resolve();
  expect(pendingResults).toHaveLength(1);
  await auth.logout();
  pendingResults.shift()!({ AccessToken: token(), ExpiresIn: 300 });
  await expect(pendingLogout).rejects.toThrow("ログイン状態が変わりました");
  expect(auth.snapshot().phase).toBe("anonymous");

  await auth.complete("user@example.invalid", "s", "123456");
  const pendingSwitch = auth.access(true);
  for (let i = 0; i < 8 && !pendingResults.length; i++) await Promise.resolve();
  expect(pendingResults).toHaveLength(1);
  await auth.begin("other@example.invalid");
  vi.mocked(value.complete).mockResolvedValueOnce({
    AccessToken: token("other", ["USER"]), RefreshToken: "other-refresh", ExpiresIn: 300,
  });
  await auth.complete("other@example.invalid", "s", "123456");
  pendingResults.shift()!({ AccessToken: token(), ExpiresIn: 300 });
  await expect(pendingSwitch).rejects.toThrow("ログイン状態が変わりました");
  expect(auth.snapshot()).toMatchObject({ phase: "authenticated", sub: "other" });
});
