/** @file admin-users.test.ts @description Nickname boundaries, ADMIN API shapes and owner-aware responses. */
import { expect, it, vi } from "vitest";
import { normalizeNickname } from "@/lib/auth/nickname";
import { adminUserListSchema, cognitoSubSchema, nicknameReceiptSchema } from "@/lib/api/schemas/adminUsers";
import { idSchema } from "@/lib/api/schemas";
import { getAdminUserFeedback, getAdminUserHistory, putAdminNickname } from "@/lib/api/adminUsers";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ request: requestMock }));
const NON_RFC_SUB = "10000000-0000-4000-e000-000000000003";

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

it("accepts non-RFC Cognito sub in list and nickname receipts but not generated IDs", () => {
  const users = [
    { userId: "10000000-0000-4000-8000-000000000001", nickname: null, email: null, enabled: true },
    { userId: NON_RFC_SUB, nickname: null, email: null, enabled: true },
  ];
  expect(adminUserListSchema.parse({ users, nextCursor: null }).users).toHaveLength(2);
  expect(nicknameReceiptSchema.parse({ userId: NON_RFC_SUB, nickname: null }).userId).toBe(NON_RFC_SUB);
  expect(() => idSchema.parse(NON_RFC_SUB)).toThrow();
  for (const invalid of ["", "not-a-sub", "../x", NON_RFC_SUB + "/history"]) {
    expect(cognitoSubSchema.safeParse(invalid).success).toBe(false);
  }
});

it("uses Cognito sub only in ADMIN user paths and preserves strict attempt IDs", async () => {
  requestMock.mockReset().mockResolvedValue({});
  await getAdminUserHistory(NON_RFC_SUB, { mode: "all", period: "all" });
  expect(requestMock.mock.calls[0][0]).toBe(
    `/admin/users/${NON_RFC_SUB}/history?mode=all&period=all&limit=5`,
  );
  await putAdminNickname(NON_RFC_SUB, "テスト");
  expect(requestMock.mock.calls[1][0]).toBe(`/admin/users/${NON_RFC_SUB}/nickname`);
  requestMock.mockResolvedValue({ feedback: {}, followUpReviews: [] });
  await getAdminUserFeedback(NON_RFC_SUB, "10000000-0000-4000-8000-000000000001");
  expect(requestMock.mock.calls[2][0]).toBe(
    `/admin/users/${NON_RFC_SUB}/attempts/10000000-0000-4000-8000-000000000001/feedback?includeFollowUpReviews=1`,
  );
  await expect(getAdminUserFeedback(NON_RFC_SUB, NON_RFC_SUB)).rejects.toThrow();
  expect(() => getAdminUserHistory("not-a-sub", { mode: "all", period: "all" })).toThrow();
});
