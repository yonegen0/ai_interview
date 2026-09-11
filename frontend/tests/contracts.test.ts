/** @file contracts.test.ts @description 入力境界・状態機械・保存の契約テスト */
import { describe, expect, it, vi } from "vitest";
import {
  answerSchema,
  questionSchema,
  feedbackSchema,
} from "@/lib/api/schemas";
import { reducer } from "@/features/interview/model/machine";
import { operationSchema, readSaved, save } from "@/lib/storage/recovery";
import { questions } from "@/mocks/data/questions";
describe("answer contract", () => {
  it.each(["", "   ", "\n\t", "あ".repeat(2001)])(
    "rejects invalid answer %s",
    (value) => expect(answerSchema.safeParse(value).success).toBe(false),
  );
  it.each([1, 99, 100, 2000])("accepts %i characters", (size) =>
    expect(answerSchema.safeParse("あ".repeat(size)).success).toBe(true),
  );
  it("validates question enums and required fields", () => {
    expect(
      questionSchema.safeParse({ ...questions[0], category: "unknown" })
        .success,
    ).toBe(false);
    expect(questionSchema.safeParse({}).success).toBe(false);
  });
  it("rejects invalid feedback score", () =>
    expect(feedbackSchema.safeParse({ score: 101 }).success).toBe(false));
});
it("allows only valid operation transitions", () => {
  expect(reducer("answering", "COMPLETE")).toBe("answering");
  expect(reducer(reducer("answering", "SUBMIT"), "UNKNOWN")).toBe(
    "recovery_required",
  );
  expect(reducer(reducer("submitting", "ACCEPT"), "FAIL")).toBe("failed");
  expect(reducer("failed", "RETRY")).toBe("answering");
  expect(reducer("completed", "SUBMIT")).toBe("completed");
});
it("restores validated storage and discards corrupt data", () => {
  const value = { version: 1, key: crypto.randomUUID(), category: "career" };
  save("test", value);
  expect(readSaved("test", operationSchema)).toEqual(value);
  sessionStorage.setItem("test", "not json");
  expect(readSaved("test", operationSchema)).toBeNull();
  expect(sessionStorage.getItem("test")).toBeNull();
});
it("storage write failure is recoverable", () => {
  const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("quota");
  });
  expect(save("test", {})).toBe(false);
  spy.mockRestore();
});
