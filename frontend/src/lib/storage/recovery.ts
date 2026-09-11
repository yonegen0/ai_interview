/** @file recovery.ts @description バージョン付きタブ内保存と失敗通知 */
import { z } from "zod";
import { idSchema, submitSchema, categorySchema } from "@/lib/api/schemas";
export const recoverySchema = z.object({
  version: z.literal(1),
  questionId: idSchema,
  context: z.string(),
  draft: z.string(),
  pending: z.object({ key: idSchema, body: submitSchema }).optional(),
});
export const operationSchema = z.object({
  version: z.literal(1),
  key: idSchema,
  category: categorySchema.optional(),
  fromAttemptId: idSchema.optional(),
});
let available = true;
const listeners = new Set<() => void>();
const fail = () => {
  available = false;
  listeners.forEach((listener) => listener());
};
export const storageAvailable = () => available;
export const subscribeStorage = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
export function readSaved<T>(key: string, schema: z.ZodType<T>): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const result = schema.safeParse(JSON.parse(raw));
    if (result.success) return result.data;
    sessionStorage.removeItem(key);
  } catch {
    try {
      sessionStorage.removeItem(key);
    } catch {
      fail();
    }
  }
  return null;
}
export function save(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    fail();
    return false;
  }
}
export function removeSaved(key: string) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    fail();
  }
}
