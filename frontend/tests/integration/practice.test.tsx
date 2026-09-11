/** @file practice.test.tsx @description 回答フォームを実API ClientとMSWで統合検証 */
import { afterAll, afterEach, beforeAll, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import { createRepository } from "@/mocks/store";
import { createHandlers, type Scenario } from "@/mocks/handlers";
import { createSession, getQuestion } from "@/lib/api/interview";
import { PracticeForm } from "@/features/interview/components/templates/PracticeForm";
import { theme } from "@/theme/theme";
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));
const repository = createRepository();
let scenario: Scenario = "success";
const server = setupServer(
  ...createHandlers(repository, () => scenario, "http://localhost/api"),
);
beforeAll(() => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost/api");
  server.listen();
});
afterEach(() => {
  repository.reset();
  scenario = "success";
  sessionStorage.clear();
  push.mockClear();
});
afterAll(() => {
  server.close();
  vi.unstubAllEnvs();
});
async function mount() {
  const created = await createSession("career", crypto.randomUUID());
  const session = await getQuestion(created.sessionId);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={client}>
        <PracticeForm session={session} retryFrom={null} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}
it("submits once on rapid form submission and reaches feedback", async () => {
  const view = await mount();
  const user = userEvent.setup();
  await user.type(
    screen.getByLabelText("あなたの回答"),
    "チームで改善しました。",
  );
  const form = screen
    .getByRole("button", { name: "回答を送信" })
    .closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  await screen.findByText("回答を確認しています");
  await waitFor(
    () =>
      expect(push).toHaveBeenCalledWith(
        expect.stringContaining("/result/?attemptId="),
      ),
    { timeout: 8000 },
  );
  expect(Object.keys(repository.read().attempts)).toHaveLength(1);
  view.unmount();
}, 12000);
it("retains immutable pending request after response loss", async () => {
  await mount();
  scenario = "response_lost";
  await userEvent.type(screen.getByLabelText("あなたの回答"), "回答です。");
  await userEvent.click(screen.getByRole("button", { name: "回答を送信" }));
  const retry = await screen.findByRole("button", { name: "送信結果を再確認" });
  expect(screen.getByLabelText("あなたの回答")).toBeDisabled();
  await userEvent.click(retry);
  await screen.findByText("回答を確認しています");
  expect(Object.keys(repository.read().attempts)).toHaveLength(1);
});
