/** @file rememberedEmail.ts @description Optional, non-credential login email convenience storage. */
import { loginSchema } from "@/features/auth/model/login";
import { mockAuth } from "./session";

const PREFIX = "pocket:login:last-email:";

function storageKey(): string | null {
  if (typeof window === "undefined") return null;
  if (mockAuth()) return `${PREFIX}mock`;
  const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID;
  return clientId ? `${PREFIX}${clientId}` : null;
}

function validEmail(value: string): boolean {
  return value.length <= 254 && loginSchema.shape.email.safeParse(value).success;
}

/** Invalid or inaccessible saved values are never restored. */
export function getRememberedEmail(): string | null {
  const key = storageKey();
  if (!key) return null;
  try {
    const value = window.localStorage.getItem(key);
    if (value === null) return null;
    if (validEmail(value)) return value;
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* Best-effort cleanup only; authentication must keep working. */
    }
  } catch {
    /* localStorage may be blocked by privacy settings or browser policy. */
  }
  return null;
}

/** Returns success without affecting authentication or session storage. */
export function saveRememberedEmail(email: string): boolean {
  const key = storageKey();
  if (!key || !validEmail(email)) return false;
  try {
    window.localStorage.setItem(key, email);
    return true;
  } catch {
    return false;
  }
}

/** Only report success after the saved value is confirmed absent. */
export function clearRememberedEmail(): boolean {
  const key = storageKey();
  if (!key) return false;
  try {
    window.localStorage.removeItem(key);
    return window.localStorage.getItem(key) === null;
  } catch {
    return false;
  }
}
