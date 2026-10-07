/** @file recovery.ts @description バージョン付きタブ内保存と失敗通知 */
import { z } from "zod";
import {
  idSchema,
  submitSchema,
  categorySchema,
  createSchema,
} from "@/lib/api/schemas";
import { auth } from "@/lib/auth/session";
import { markStorageUnavailable as fail } from "./status";
export { storageAvailable, subscribeStorage } from "./status";
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
  body: createSchema.optional(),
});
export function scopedKey(key: string, scope = auth.scope()) {
  if (key.startsWith("pocket:mock:")) return key;
  return scope ? scope + key : null;
}
const memory = new Map<string, string | null>();
const dirty = new Set<string>();
export function readSaved<T>(
  key: string,
  schema: z.ZodType<T>,
  scope = auth.scope(),
): T | null {
  const target = scopedKey(key, scope);
  if (!target) return null;
  let raw: string | null | undefined;
  if (dirty.has(target)) raw = memory.get(target);
  else {
    try {
      raw = sessionStorage.getItem(target);
    } catch {
      fail();
      raw = memory.get(target);
    }
  }
  if (!raw) return null;
  try {
    const parsed = schema.safeParse(JSON.parse(raw));
    if (parsed.success) return parsed.data;
  } catch {
    /* Invalid data is not a storage availability failure. */
  }
  removeSaved(key, scope);
  return null;
}
export function save(key: string, value: unknown, scope = auth.scope()) {
  const target = scopedKey(key, scope);
  if (!target) return false;
  const raw = JSON.stringify(value);
  memory.set(target, raw);
  try {
    sessionStorage.setItem(target, raw);
    dirty.delete(target);
    return true;
  } catch {
    dirty.add(target);
    fail();
    return false;
  }
}
export function removeSaved(key: string, scope = auth.scope()) {
  const target = scopedKey(key, scope);
  if (!target) return;
  try {
    sessionStorage.removeItem(target);
    memory.delete(target);
    dirty.delete(target);
  } catch {
    memory.set(target, null);
    dirty.add(target);
    fail();
  }
}
/** Bind storage to an operation's original user, never to a later login. */
export function recoveryForScope(scope: string | null) {
  return {
    readSaved: <T>(key: string, schema: z.ZodType<T>) =>
      readSaved(key, schema, scope),
    save: (key: string, value: unknown) => save(key, value, scope),
    removeSaved: (key: string) => removeSaved(key, scope),
  };
}
/** Story/unit isolation only. Does not change persisted user data. */
export function resetRecoveryMemoryForTests() {
  memory.clear();
  dirty.clear();
}
