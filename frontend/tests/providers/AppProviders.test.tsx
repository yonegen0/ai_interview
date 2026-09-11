/** @file AppProviders.test.tsx @description Mock起動境界とQuery既定値のProviderテスト。 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const browserMock = vi.hoisted(() => ({ startMock: vi.fn() }));
vi.mock("@/mocks/browser", () => browserMock);

describe("AppProviders", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    browserMock.startMock.mockReset();
  });

  it("Mock無効時はchildrenをすぐ表示する", async () => {
    vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "false");
    const { AppProviders } = await import("@/providers/AppProviders");
    render(<AppProviders><p>子要素</p></AppProviders>);
    expect(screen.getByText("子要素")).toBeInTheDocument();
    expect(browserMock.startMock).not.toHaveBeenCalled();
  });

  it("Mock起動完了まで待機し、完了後にchildrenを表示する", async () => {
    vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "true");
    browserMock.startMock.mockResolvedValue(undefined);
    const { AppProviders } = await import("@/providers/AppProviders");
    render(<AppProviders><p>子要素</p></AppProviders>);
    expect(screen.getByRole("status")).toHaveTextContent("練習環境を準備しています");
    await waitFor(() => expect(screen.getByText("子要素")).toBeInTheDocument());
    expect(screen.getByText(/評価は固定サンプル/)).toBeInTheDocument();
  });

  it("Mock起動失敗をAlertで案内する", async () => {
    vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "true");
    browserMock.startMock.mockRejectedValue(new Error("worker failed"));
    const { AppProviders } = await import("@/providers/AppProviders");
    render(<AppProviders><p>子要素</p></AppProviders>);
    await waitFor(() => expect(screen.getByText(/Mockを起動できませんでした/)).toBeInTheDocument());
    expect(screen.queryByText("子要素")).not.toBeInTheDocument();
  });

  it("GETだけ最大1回再試行し、Mutationは再試行しない", async () => {
    vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "false");
    const { createAppQueryClient } = await import("@/providers/AppProviders");
    const { ApiError } = await import("@/lib/api/client");
    const options = createAppQueryClient().getDefaultOptions();
    const retry = options.queries?.retry;
    expect(typeof retry).toBe("function");
    if (typeof retry === "function") {
      expect(retry(0, new ApiError("INTERNAL_SERVER_ERROR", 500))).toBe(true);
      expect(retry(1, new ApiError("INTERNAL_SERVER_ERROR", 500))).toBe(false);
      expect(retry(0, new ApiError("VALIDATION_ERROR", 400))).toBe(false);
    }
    expect(options.mutations?.retry).toBe(false);
  });
});
