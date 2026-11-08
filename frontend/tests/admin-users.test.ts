/** @file admin-users.test.ts @description Nickname boundaries, ADMIN API shapes and owner-aware responses. */
import { expect, it } from "vitest";
import { normalizeNickname } from "@/lib/auth/nickname";
import { adminUserListSchema, nicknameReceiptSchema } from "@/lib/api/schemas/adminUsers";

it.each([
  ["", ""],
  [" あいう ", "あいう"],
  ["e\u0301", "é"],
  ["👩‍💻", "👩‍💻"],
  ["あ".repeat(24), "あ".repeat(24)],
  ["🌸".repeat(24), "🌸".repeat(24)],
])("normalizes nickname %s", (input, expected) => {
  expect(normalizeNickname(input)).toBe(expected);
  expect(Array.from(expected).length).toBeLessThanOrEqual(24);
});
it.each([
  [null], [12], ["a".repeat(25)], ["あ".repeat(25)],
  ["hello\nworld"], ["hello\rworld"], ["a\0b"],
])("rejects invalid nickname %s", (value) => {
  expect(() => normalizeNickname(value)).toThrow();
});
it("permits duplicate nicknames and validates ADMIN list fields", () => {
  const users = [
    { userId: "10000000-0000-4000-8000-000000000001", nickname: "かずき",
      email: "user1@example.invalid", enabled: true },
    { userId: "10000000-0000-4000-8000-000000000002", nickname: "かずき",
      email: "user2@example.invalid", enabled: false },
  ];
  expect(adminUserListSchema.parse({ users, nextCursor: "token" }).users).toHaveLength(2);
  expect(nicknameReceiptSchema.parse({ userId: users[0].userId, nickname: null }).nickname).toBeNull();
  expect(() => adminUserListSchema.parse({
    users: [{ ...users[0], accessToken: "forbidden" }], nextCursor: null,
  })).toThrow();
});
