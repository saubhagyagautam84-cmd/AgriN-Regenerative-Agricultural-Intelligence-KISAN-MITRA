/**
 * Session token storage - split out from AuthContext.tsx so lib/api.ts can
 * read the token for authenticated requests (family members) without a
 * circular import (AuthContext already imports API_BASE from lib/api.ts).
 */
export const SESSION_STORAGE_KEY = "kisan-mitra-session";

export function getStoredSessionToken(): string | null {
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredSessionToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(SESSION_STORAGE_KEY, token);
    else window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Best-effort only.
  }
}
