/** @file history-ui.test.tsx @description 履歴の型・0点・JST表示とメニュー操作。 */
import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";
import { expect, it, vi } from "vitest";
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
