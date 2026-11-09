/** @file remembered-email.test.ts @description Remembered email is optional and isolated from authentication credentials. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearRememberedEmail,
  getRememberedEmail,
  saveRememberedEmail,
} from "@/lib/auth/rememberedEmail";

const mockKey = "pocket:login:last-email:mock";
const realKey = "pocket:login:last-email:synthetic-client";

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "true");
  localStorage.removeItem(mockKey);
  localStorage.removeItem(realKey);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  localStorage.removeItem(mockKey);
  localStorage.removeItem(realKey);
});

describe("remembered login email", () => {
  it("returns null for a missing value", () => {
    expect(getRememberedEmail()).toBeNull();
  });
  it("saves, retrieves and overwrites just the last successful email", () => {
    expect(saveRememberedEmail("user@example.invalid")).toBe(true);
    expect(getRememberedEmail()).toBe("user@example.invalid");
    expect(saveRememberedEmail("admin@example.invalid")).toBe(true);
    expect(localStorage.getItem(mockKey)).toBe("admin@example.invalid");
  });
  it("removes the remembered email without touching other local storage", () => {
    localStorage.setItem("unrelated", "preserve");
    saveRememberedEmail("user@example.invalid");
    expect(clearRememberedEmail()).toBe(true);
    expect(getRememberedEmail()).toBeNull();
    expect(localStorage.getItem("unrelated")).toBe("preserve");
    localStorage.removeItem("unrelated");
  });
  it.each(["", "invalid", "user@@example.invalid", `${"a".repeat(250)}@example.invalid`])(
    "rejects invalid or overlong email values",
    (value) => {
      expect(saveRememberedEmail(value)).toBe(false);
      localStorage.setItem(mockKey, value);
      expect(getRememberedEmail()).toBeNull();
      expect(localStorage.getItem(mockKey)).toBeNull();
    },
  );
  it("does not let an invalid saved value survive if cleanup throws", () => {
    localStorage.setItem(mockKey, "invalid");
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw Error("blocked"); });
    expect(getRememberedEmail()).toBeNull();
    expect(localStorage.getItem(mockKey)).toBe("invalid");
  });
  it("does not propagate a storage read failure", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw Error("blocked"); });
    expect(getRememberedEmail()).toBeNull();
  });
  it("does not propagate a storage write failure", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw Error("blocked"); });
    expect(saveRememberedEmail("user@example.invalid")).toBe(false);
  });
  it("does not treat failed deletion as success", () => {
    saveRememberedEmail("user@example.invalid");
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw Error("blocked"); });
    expect(clearRememberedEmail()).toBe(false);
    expect(localStorage.getItem(mockKey)).toBe("user@example.invalid");
  });
  it("checks that the key actually disappeared after deletion", () => {
    saveRememberedEmail("user@example.invalid");
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => undefined);
    expect(clearRememberedEmail()).toBe(false);
  });
  it("isolates real Cognito client IDs from Mock", () => {
    expect(saveRememberedEmail("user@example.invalid")).toBe(true);
    vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "false");
    vi.stubEnv("NEXT_PUBLIC_COGNITO_CLIENT_ID", "synthetic-client");
    expect(getRememberedEmail()).toBeNull();
    expect(saveRememberedEmail("admin@example.invalid")).toBe(true);
    expect(localStorage.getItem(realKey)).toBe("admin@example.invalid");
    vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "true");
    expect(getRememberedEmail()).toBe("user@example.invalid");
  });
  it("does not access storage with a missing Cognito client ID", () => {
    vi.stubEnv("NEXT_PUBLIC_MSW_ENABLED", "false");
    vi.stubEnv("NEXT_PUBLIC_COGNITO_CLIENT_ID", "");
    const spy = vi.spyOn(Storage.prototype, "getItem");
    expect(getRememberedEmail()).toBeNull();
    expect(saveRememberedEmail("user@example.invalid")).toBe(false);
    expect(clearRememberedEmail()).toBe(false);
    expect(spy).not.toHaveBeenCalled();
    expect(localStorage.getItem("pocket:login:last-email:unconfigured")).toBeNull();
  });
  it("never touches storage during SSR", () => {
    vi.stubGlobal("window", undefined);
    expect(getRememberedEmail()).toBeNull();
    expect(saveRememberedEmail("user@example.invalid")).toBe(false);
    expect(clearRememberedEmail()).toBe(false);
  });
});
