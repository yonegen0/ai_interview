/** @file remembered-email-login.test.tsx @description Login integration using the existing Mock Cognito adapter. */
import { useLayoutEffect, useRef } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { LoginPage } from "@/features/auth/components/pages/LoginPage";
import { useEmailOtpLogin } from "@/features/auth/hooks/useEmailOtpLogin";
import { auth } from "@/lib/auth/session";
import { saveRememberedEmail } from "@/lib/auth/rememberedEmail";

const navigation = vi.hoisted(() => ({ replace: vi.fn(), returnTo: "/practice/" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigation.replace }),
  useSearchParams: () => new URLSearchParams({ returnTo: navigation.returnTo }),
}));

const key = "pocket:login:last-email:mock";
const mount = (node = <LoginPage />) => render(
  <QueryClientProvider client={new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })}>
    {node}
  </QueryClientProvider>,
);

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.removeItem(key);
  navigation.replace.mockReset();
  navigation.returnTo = "/practice/";
});

async function requestCode(email: string) {
  const user = userEvent.setup();
  const input = screen.getByLabelText("メールアドレス");
  await user.clear(input);
  await user.type(input, email);
  await user.click(screen.getByRole("button", { name: "確認コードを送る" }));
  await screen.findByLabelText("確認コード");
  return user;
}
async function finishLogin(user: ReturnType<typeof userEvent.setup>, code = "123456") {
  await user.type(screen.getByLabelText("確認コード"), code);
  await user.click(screen.getByRole("button", { name: "ログインする" }));
}

it("restores a saved email without sending an OTP, then permits deletion", async () => {
  saveRememberedEmail("user@example.invalid");
  mount();
  await waitFor(() => expect(screen.getByLabelText("メールアドレス")).toHaveValue("user@example.invalid"));
  expect(screen.queryByLabelText("確認コード")).not.toBeInTheDocument();
  expect(auth.snapshot().phase).not.toBe("challenge");
  await userEvent.click(screen.getByRole("button", { name: "保存したメールアドレスを削除" }));
  expect(localStorage.getItem(key)).toBeNull();
  expect(screen.getByLabelText("メールアドレス")).toHaveValue("");
  expect(screen.queryByRole("button", { name: "保存したメールアドレスを削除" })).not.toBeInTheDocument();
});

it("leaves an empty email field when there is no stored value", () => {
  mount();
  expect(screen.getByLabelText("メールアドレス")).toHaveValue("");
  expect(screen.queryByRole("button", { name: "保存したメールアドレスを削除" })).not.toBeInTheDocument();
});

function DirtyProbe() {
  const { form, actions } = useEmailOtpLogin();
  return (
    <>
      <output aria-label="dirty">{String(form.formState.isDirty)}</output>
      <input aria-label="probe-email" value={form.watch("email")}
        onChange={(event) => {
          actions.emailEdited();
          form.setValue("email", event.target.value, { shouldDirty: true });
        }} />
    </>
  );
}
it("treats restored email as a pristine form default and does not restore twice", async () => {
  saveRememberedEmail("user@example.invalid");
  mount(<DirtyProbe />);
  await waitFor(() => expect(screen.getByLabelText("probe-email")).toHaveValue("user@example.invalid"));
  expect(screen.getByLabelText("dirty")).toHaveTextContent("false");
  fireEvent.change(screen.getByLabelText("probe-email"), { target: { value: "edited@example.invalid" } });
  expect(screen.getByLabelText("dirty")).toHaveTextContent("true");
  expect(screen.getByLabelText("probe-email")).toHaveValue("edited@example.invalid");
});

function EarlyTypingProbe() {
  const { form, actions } = useEmailOtpLogin();
  const once = useRef(false);
  useLayoutEffect(() => {
    if (once.current) return;
    once.current = true;
    actions.emailEdited();
    form.setValue("email", "manual@example.invalid", { shouldDirty: true });
  }, [form, actions]);
  return <output aria-label="early-email">{form.watch("email")}</output>;
}
it("never overwrites input made before the passive restore effect", async () => {
  saveRememberedEmail("user@example.invalid");
  mount(<EarlyTypingProbe />);
  await waitFor(() => expect(screen.getByLabelText("early-email")).toHaveTextContent("manual@example.invalid"));
});

it("only saves after completed OTP and preserves the requested returnTo", async () => {
  navigation.returnTo = "/practice/session/";
  mount();
  const user = await requestCode("admin@example.invalid");
  expect(localStorage.getItem(key)).toBeNull();
  expect(screen.queryByRole("button", { name: "保存したメールアドレスを削除" })).not.toBeInTheDocument();
  await finishLogin(user);
  await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/practice/session/"));
  expect(localStorage.getItem(key)).toBe("admin@example.invalid");
  expect(auth.snapshot().groups).toContain("ADMIN");
});

it("retains previous stored email if OTP completion fails", async () => {
  saveRememberedEmail("user@example.invalid");
  mount();
  const user = await requestCode("another@example.invalid");
  expect(localStorage.getItem(key)).toBe("user@example.invalid");
  await finishLogin(user, "000000");
  expect(await screen.findByText(/コードまたは有効期限を確認/)).toBeInTheDocument();
  expect(localStorage.getItem(key)).toBe("user@example.invalid");
  expect(navigation.replace).not.toHaveBeenCalled();
});

it("navigates on successful authentication even if local storage cannot save", async () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw Error("blocked"); });
  mount();
  const user = await requestCode("user@example.invalid");
  await finishLogin(user);
  await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/practice/"));
});

it("reports deletion failure without clearing the email or disabling login", async () => {
  saveRememberedEmail("user@example.invalid");
  mount();
  await waitFor(() => expect(screen.getByLabelText("メールアドレス")).toHaveValue("user@example.invalid"));
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw Error("blocked"); });
  await userEvent.click(screen.getByRole("button", { name: "保存したメールアドレスを削除" }));
  expect(screen.getByText("保存したメールアドレスを削除できませんでした。")).toBeInTheDocument();
  expect(screen.getByLabelText("メールアドレス")).toHaveValue("user@example.invalid");
  expect(screen.getByRole("button", { name: "確認コードを送る" })).toBeEnabled();
  expect(localStorage.getItem(key)).toBe("user@example.invalid");
});

it("overwrites the last remembered ADMIN email only after USER logs in", async () => {
  saveRememberedEmail("admin@example.invalid");
  const first = mount();
  await waitFor(() => expect(screen.getByLabelText("メールアドレス")).toHaveValue("admin@example.invalid"));
  first.unmount();
  await auth.logout();
  mount();
  const user = await requestCode("user@example.invalid");
  expect(localStorage.getItem(key)).toBe("admin@example.invalid");
  await finishLogin(user);
  await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/practice/"));
  expect(localStorage.getItem(key)).toBe("user@example.invalid");
  expect(auth.snapshot().groups).toContain("USER");
});
