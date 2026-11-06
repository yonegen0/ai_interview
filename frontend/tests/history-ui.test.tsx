/** @file history-ui.test.tsx @description 履歴の型・0点・JST表示とメニュー操作。 */
import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useHistory } from "@/features/history/hooks/useHistory";
import { getHistory } from "@/lib/api/history";
import { getQuota } from "@/lib/api/star";
import { mockHistory } from "@/mocks/history";
import { createRepository } from "@/mocks/store";
import { starRoute } from "@/mocks/star";
import { emptyStarInput } from "@/lib/api/schemas/star";
import type { HistoryMode, HistoryPeriod } from "@/lib/api/schemas/history";

vi.mock("@/lib/api/history", () => ({ getHistory: vi.fn() }));
vi.mock("@/lib/api/star", () => ({ getQuota: vi.fn() }));
import { AccountActionsView } from "@/components/molecules/AccountActionsView";
import { HistoryList, formatHistoryDate } from "@/features/history/components/HistoryList";
import { historyResponseSchema, type HistoryItem } from "@/lib/api/schemas/history";
import { theme } from "@/theme/theme";

const id = "10000000-0000-4000-8000-000000000001";
const item: HistoryItem = {
  id: `attempt:${id}`, kind: "normal", label: "志望動機",
  category: "motivation", createdAt: Date.parse("2026-11-05T15:30:00Z"),
  status: "completed", score: 0, scoreMax: 100,
  attemptId: id, evaluationId: id, generationId: null, assistType: null,
};
const wrapper = ({ children }: { children: React.ReactNode }) =>
  <ThemeProvider theme={theme}>{children}</ThemeProvider>;

it("validates genuine zero scores separately from absent scores", () => {
  const assist = { ...item, id: `assist:${id}`, kind: "assist", status: "SUCCEEDED",
    attemptId: null, evaluationId: null, generationId: id,
    assistType: "star", score: null, scoreMax: null };
  expect(historyResponseSchema.safeParse({
    items: [item, assist], nextCursor: null, usage: null,
  }).success).toBe(true);
  expect(historyResponseSchema.safeParse({
    items: [{ ...assist, score: 85 }], nextCursor: null, usage: null,
  }).success).toBe(false);
});

it("displays a Japanese date, score scale, and detail action", () => {
  expect(formatHistoryDate(item.createdAt)).toContain("2026/11/06");
  const select = vi.fn();
  render(<HistoryList items={[item]} loading={false} error={null}
    loadingMore={false} hasMore={false} onLoadMore={vi.fn()}
    onRetry={vi.fn()} onSelect={select} />, { wrapper });
  expect(screen.getByText("0/100点")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "志望動機の詳細を見る" }));
  expect(select).toHaveBeenCalledWith(item);
});

it("opens account menu and runs history action without signing out", () => {
  const onHistory = vi.fn();
  const onLogout = vi.fn();
  render(<AccountActionsView authenticated admin sub={id} phase="authenticated"
    onHistory={onHistory} onLogout={onLogout} />, { wrapper });
  fireEvent.click(screen.getByRole("button", { name: "アカウントメニュー" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "利用履歴" }));
  expect(onHistory).toHaveBeenCalledTimes(1);
  expect(onLogout).not.toHaveBeenCalled();
});


const completeUsage = {
  practiceAttempts: 2, evaluatedAttempts: 1, assistGenerations: 1,
  normalAverage: 80, coachingAverage: null,
};
const quotaSnapshot = {
  month: "2026-11",
  user: { consumed: 1, reserved: 0, remaining: 19 },
  global: { consumed: 1, reserved: 0, remaining: 599 },
};
const queryWrapper = (client: QueryClient) =>
  ({ children }: { children: React.ReactNode }) =>
    <QueryClientProvider client={client}>{children}</QueryClientProvider>;

it("reuses complete all-period history usage without a duplicate API request", async () => {
  vi.clearAllMocks();
  vi.mocked(getHistory).mockResolvedValue({
    items: [], nextCursor: null, usage: completeUsage,
  });
  vi.mocked(getQuota).mockResolvedValue(quotaSnapshot);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { rerender, result, unmount } = renderHook(
    ({ tab, mode, period }: { tab: number; mode: HistoryMode; period: HistoryPeriod }) =>
      useHistory("owner-a", true, mode, period, tab),
    { initialProps: { tab: 0, mode: "all" as HistoryMode, period: "all" as HistoryPeriod },
      wrapper: queryWrapper(client) },
  );
  await waitFor(() => expect(result.current.records.data?.pages[0].usage).toEqual(completeUsage));
  expect(getHistory).toHaveBeenCalledTimes(1);
  expect(getQuota).not.toHaveBeenCalled();
  rerender({ tab: 1, mode: "all", period: "all" });
  await waitFor(() => expect(getQuota).toHaveBeenCalledTimes(1));
  expect(getHistory).toHaveBeenCalledTimes(1);
  expect(result.current.usage.fetchStatus).toBe("idle");
  unmount();
  client.clear();
});

it("fetches usage on demand without refetching it for history filters", async () => {
  vi.clearAllMocks();
  vi.mocked(getHistory).mockResolvedValue({
    items: [], nextCursor: null, usage: completeUsage,
  });
  vi.mocked(getQuota).mockResolvedValue(quotaSnapshot);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { rerender, unmount } = renderHook(
    ({ tab, mode }: { tab: number; mode: HistoryMode }) =>
      useHistory("owner-a", true, mode, "today", tab),
    { initialProps: { tab: 0, mode: "normal" as HistoryMode },
      wrapper: queryWrapper(client) },
  );
  await waitFor(() => expect(getHistory).toHaveBeenCalledTimes(1));
  expect(getQuota).not.toHaveBeenCalled();
  rerender({ tab: 1, mode: "normal" });
  await waitFor(() => expect(getHistory).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(getQuota).toHaveBeenCalledTimes(1));
  rerender({ tab: 1, mode: "coaching" });
  expect(getHistory).toHaveBeenCalledTimes(2);
  unmount();
  client.clear();
});

it("retains mock assist history after TTL but refuses expired generation details", () => {
  const now = Date.parse("2026-11-06T06:00:00Z");
  const id = crypto.randomUUID();
  const state = createRepository().read();
  state.star.historySummaries[id] = {
    owner: "owner-a", generationId: id, question: "強みを教えてください",
    assistType: "prep", createdAt: now - 10_000, status: "SUCCEEDED",
  };
  state.star.generations[id] = {
    generationId: id, status: "SUCCEEDED", generationTargetCategory: null,
    result: null, owner: "owner-a", contextId: crypto.randomUUID(),
    starDraftId: crypto.randomUUID(), input: emptyStarInput("prep"),
    question: "強みを教えてください", month: "2026-11",
    quotaState: "consumed", callStarted: true,
    deadlineAt: now + 890_000, leaseUntil: null, executionId: null,
    expiresAt: Math.floor(now / 1000) - 1,
  };
  const history = mockHistory(state, "owner-a", { mode: "assist" }, now);
  expect(history.items).toHaveLength(1);
  expect(history.items[0]).toMatchObject({
    generationId: id, assistType: "prep", status: "SUCCEEDED",
  });
  expect(mockHistory(state, "owner-b", { mode: "assist" }, now).items).toHaveLength(0);
  expect(() => starRoute(state, "owner-a", "GET",
    `/star-assist/generations/${id}`, null, null, now)).toThrow();
});
