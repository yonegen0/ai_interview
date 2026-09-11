/** @file evaluation.test.tsx @description 評価ポーリングの停止と手動確認 */
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { useEvaluation } from "@/features/interview/hooks/useEvaluation";
import { getEvaluation } from "@/lib/api/interview";
vi.mock("@/lib/api/interview", () => ({ getEvaluation: vi.fn() }));
const id = "00000000-0000-4000-8000-000000000001";
const mount = () => {
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(({ evaluationId }) => useEvaluation(evaluationId), {
    wrapper,
    initialProps: { evaluationId: id },
  });
};
const advance = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
it.each(["completed", "failed"] as const)(
  "stops polling and elapsed timer after %s and unmount",
  async (status) => {
    vi.useFakeTimers();
    vi.mocked(getEvaluation).mockResolvedValue({
      evaluationId: id,
      attemptId: id,
      status,
      error: { code: "EVALUATION_FAILED", message: "failed" },
    });
    const view = mount();
    await advance(100);
    const count = vi.mocked(getEvaluation).mock.calls.length;
    const elapsed = view.result.current.elapsed;
    await advance(10000);
    expect(view.result.current.elapsed).toBe(elapsed);
    expect(getEvaluation).toHaveBeenCalledTimes(count);
    view.unmount();
    await advance(10000);
    expect(getEvaluation).toHaveBeenCalledTimes(count);
  },
);
it("pauses after 120 seconds and permits manual check", async () => {
  vi.useFakeTimers();
  vi.mocked(getEvaluation).mockResolvedValue({
    evaluationId: id,
    attemptId: id,
    status: "processing",
  });
  const view = mount();
  for (let i = 0; i < 121; i++) await advance(1000);
  expect(view.result.current.paused).toBe(true);
  const count = vi.mocked(getEvaluation).mock.calls.length;
  await advance(10000);
  expect(getEvaluation).toHaveBeenCalledTimes(count);
  await act(async () => {
    await view.result.current.refetch();
  });
  expect(getEvaluation).toHaveBeenCalledTimes(count + 1);
  view.unmount();
});
it("restarts the elapsed timer when a new evaluation replaces a terminal one", async () => {
  vi.useFakeTimers();
  vi.mocked(getEvaluation).mockResolvedValue({
    evaluationId: id,
    attemptId: id,
    status: "completed",
  });
  const view = mount();
  await advance(100);
  expect(view.result.current.terminal).toBe(true);
  const nextId = "00000000-0000-4000-8000-000000000002";
  vi.mocked(getEvaluation).mockResolvedValue({
    evaluationId: nextId,
    attemptId: nextId,
    status: "processing",
  });
  view.rerender({ evaluationId: nextId });
  await advance(100);
  expect(view.result.current.terminal).toBe(false);
  expect(view.result.current.elapsed).toBe(0);
  await advance(2000);
  expect(view.result.current.elapsed).toBe(2);
  view.unmount();
});
it("pauses in background and offline, resumes when visible and online", async () => {
  vi.useFakeTimers();
  vi.mocked(getEvaluation).mockResolvedValue({
    evaluationId: id,
    attemptId: id,
    status: "processing",
  });
  const visibility = vi.spyOn(document, "visibilityState", "get");
  const online = vi.spyOn(navigator, "onLine", "get");
  const view = mount();
  await advance(100);
  act(() => {
    visibility.mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
  });
  const count = vi.mocked(getEvaluation).mock.calls.length;
  await advance(5000);
  expect(getEvaluation).toHaveBeenCalledTimes(count);
  act(() => {
    visibility.mockReturnValue("visible");
    online.mockReturnValue(false);
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("offline"));
  });
  await advance(5000);
  expect(getEvaluation).toHaveBeenCalledTimes(count);
  act(() => {
    online.mockReturnValue(true);
    window.dispatchEvent(new Event("online"));
  });
  await advance(100);
  expect(vi.mocked(getEvaluation).mock.calls.length).toBeGreaterThan(count);
  view.unmount();
});
