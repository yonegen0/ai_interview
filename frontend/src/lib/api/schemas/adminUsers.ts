/** @file adminUsers.ts @description ADMIN-only user listing and nickname API contracts. */
import { z } from "zod";
export const adminUserSchema = z.object({
  userId: z.uuid(), nickname: z.string().nullable(), email: z.string().nullable(),
  enabled: z.boolean(),
}).strict();
export type AdminUser = z.infer<typeof adminUserSchema>;
export const adminUserListSchema = z.object({
  users: z.array(adminUserSchema).max(60),
  nextCursor: z.string().nullable(),
}).strict();
export const nicknameReceiptSchema = adminUserSchema.pick({ userId: true, nickname: true });
