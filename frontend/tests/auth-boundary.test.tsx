/** @file auth-boundary.test.tsx @description Verified refresh and manual recheck keep the auth boundary safe. */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AuthBoundary } from "@/components/organisms/AuthBoundary";
import { AccountActionsView } from "@/components/molecules/AccountActionsView";
import { auth, setIdentityAdapterForTests } from "@/lib/auth/session";
import type { IdentityAdapter } from "@/lib/auth/cognito";

vi.mock("next/navigation", () => ({
  usePathname: () => "/practice/session/",
  useSearchParams: () => new URLSearchParams(),
}));

function configure() {
  vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "false");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_REGION", "ap-northeast-1");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_CLIENT_ID", "synthetic-client");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_USER_POOL_ID", "ap-northeast-1_synthetic");
}
function token() {
  return `header.${btoa(JSON.stringify({
    sub: "user",
    "cognito:groups": ["USER"],
    client_id: "synthetic-client",
    token_use: "access",
    iss: "https://cognito-idp.ap-northeast-1.amazonaws.com/ap-northeast-1_synthetic",
  }))}.synthetic`;
}
function makeAdapter(refresh: IdentityAdapter["refresh"]): IdentityAdapter {
  return {
    begin: vi.fn(async () => "challenge"),
    complete: vi.fn(async () => ({
      AccessToken: token(), RefreshToken: "synthetic-refresh", ExpiresIn: 300,
    })),
    refresh,
    revoke: vi.fn(async () => undefined),
  };
}
async function signIn(adapter: IdentityAdapter) {
  configure();
  setIdentityAdapterForTests(adapter);
  await auth.complete("user@example.invalid", "challenge", "123456");
}
afterEach(async () => {
  await auth.logout();
  setIdentityAdapterForTests(null);
  sessionStorage.clear();
  vi.unstubAllEnvs();
});

it("keeps the same answer input mounted while a verified session refreshes", async () => {
  let finish: ((result: Awaited<ReturnType<IdentityAdapter["refresh"]>>) => void) | undefined;
  const refresh = vi.fn(() => new Promise<Awaited<ReturnType<IdentityAdapter["refresh"]>>>((resolve) => {
    finish = resolve;
  }));
  await signIn(makeAdapter(refresh));
  render(<AuthBoundary><input aria-label="練習回答" defaultValue="編集中の下書き" /></AuthBoundary>);
  const input = screen.getByRole("textbox", { name: "練習回答" });
  let pending: Promise<string> | undefined;
  act(() => { pending = auth.access(true); });
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  expect(auth.snapshot().phase).toBe("refreshing");
  expect(screen.getByRole("textbox", { name: "練習回答" })).toBe(input);
  expect(input).toHaveValue("編集中の下書き");
  expect(screen.queryByText("ログインして練習を始めましょう。")).not.toBeInTheDocument();
  await act(async () => {
    finish!({ AccessToken: token(), ExpiresIn: 300 });
    await pending;
  });
  expect(screen.getByRole("textbox", { name: "練習回答" })).toBe(input);
});

it("blocks content during an auth outage and restores it through manual recheck", async () => {
  let finish: ((result: Awaited<ReturnType<IdentityAdapter["refresh"]>>) => void) | undefined;
  const refresh = vi.fn(() => new Promise<Awaited<ReturnType<IdentityAdapter["refresh"]>>>((resolve) => {
    finish = resolve;
  }));
  await signIn(makeAdapter(refresh));
  render(<AuthBoundary><input aria-label="保護された回答欄" /></AuthBoundary>);
  act(() => { auth.suspend(); });
  expect(screen.queryByRole("textbox", { name: "保護された回答欄" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "認証を再確認する" }));
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  expect(refresh).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("textbox", { name: "保護された回答欄" })).not.toBeInTheDocument();
  await act(async () => {
    finish!({ AccessToken: token(), ExpiresIn: 300 });
  });
  await waitFor(() => expect(screen.getByRole("textbox", { name: "保護された回答欄" })).toBeInTheDocument());
});

it("shows the recheck action rather than a login link on transient outage", async () => {
  const retry = vi.fn();
  const { rerender } = render(
    <AccountActionsView authenticated={false} phase="temporarily_unavailable"
      onLogout={vi.fn()} onRetry={retry} />,
  );
  expect(screen.queryByText("ログイン")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "認証を再確認する" }));
  expect(retry).toHaveBeenCalledTimes(1);
  rerender(<AccountActionsView authenticated={false} phase="restoring" onLogout={vi.fn()} />);
  expect(screen.getByText("ログイン状態を確認しています…")).toBeInTheDocument();
  expect(screen.queryByText("ログイン")).not.toBeInTheDocument();
});
