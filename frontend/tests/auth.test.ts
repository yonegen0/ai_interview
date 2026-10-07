/** @file auth.test.ts @description 実認証adapter境界をstubし、期限更新と本人確認を検証。 */
import { afterEach, expect, it, vi } from "vitest";
import { auth, setIdentityAdapterForTests } from "@/lib/auth/session";
import type { IdentityAdapter } from "@/lib/auth/cognito";
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
it("deduplicates simultaneous refresh and clears authentication on failure", async () => {
  configure();
  const value = adapter();
  setIdentityAdapterForTests(value);
  await auth.complete("user@example.invalid", "session", "123456");
  await Promise.all([auth.access(true), auth.access(true), auth.access(true)]);
  expect(value.refresh).toHaveBeenCalledTimes(1);
  vi.mocked(value.refresh).mockRejectedValue(
    new Error("private service payload"),
  );
  await expect(auth.access(true)).rejects.toThrow("ログインし直してください");
  expect(auth.snapshot().sub).toBeNull();
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
