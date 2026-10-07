/** @file setup.ts @description DOMテスト後のクリーンアップ */
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";
import { resetRecoveryMemoryForTests } from "@/lib/storage/recovery";
import { auth } from "@/lib/auth/session";
import { cleanup } from "@testing-library/react";
afterEach(() => cleanup());
beforeEach(() => {
  resetRecoveryMemoryForTests();
  vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "true");
  auth.setMockActor("mock-user", ["USER"]);
});
