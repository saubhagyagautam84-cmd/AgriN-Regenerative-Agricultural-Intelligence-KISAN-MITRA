"use client";

/**
 * Real phone-OTP login: Firebase Phone Auth on the client sends/verifies the
 * SMS code, then the resulting Firebase ID token is exchanged for this app's
 * own session token at POST /api/auth/verify (backend verifies it via the
 * Firebase Admin SDK and upserts a row in SQLite - see backend/services/auth.py).
 *
 * Session token is a plain bearer token, persisted in localStorage and sent
 * as `Authorization: Bearer <token>` by lib/api.ts.
 */

import {
  RecaptchaVerifier,
  signInWithPhoneNumber,
  signOut,
  type ConfirmationResult,
} from "firebase/auth";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getFirebaseAuth, isFirebaseConfigured } from "./firebaseClient";
import { getStoredSessionToken, setStoredSessionToken } from "./session";
import { API_BASE } from "@/lib/api";

export interface AuthUser {
  phone: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  ready: boolean;
  /** Sends an OTP to `phoneE164` (e.g. "+919812345678"). `recaptchaContainerId` must be a mounted, empty DOM node id. */
  sendOtp: (phoneE164: string, recaptchaContainerId: string) => Promise<void>;
  verifyOtp: (code: string) => Promise<void>;
  logout: () => Promise<void>;
  firebaseConfigured: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [confirmation, setConfirmation] = useState<ConfirmationResult | null>(null);
  const firebaseConfigured = isFirebaseConfigured();

  useEffect(() => {
    const token = getStoredSessionToken();
    if (!token) {
      setReady(true);
      return;
    }
    fetch(`${API_BASE}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data?.phone) setUser({ phone: data.phone });
        else setStoredSessionToken(null);
      })
      .catch(() => {
        // Backend unreachable - stay logged out for this session rather than blocking the page.
      })
      .finally(() => setReady(true));
  }, []);

  const sendOtp = useCallback(async (phoneE164: string, recaptchaContainerId: string) => {
    const auth = getFirebaseAuth();
    const verifier = new RecaptchaVerifier(auth, recaptchaContainerId, { size: "invisible" });
    const result = await signInWithPhoneNumber(auth, phoneE164, verifier);
    setConfirmation(result);
  }, []);

  const verifyOtp = useCallback(
    async (code: string) => {
      if (!confirmation) throw new Error("no-otp-sent");
      const credential = await confirmation.confirm(code);
      const idToken = await credential.user.getIdToken();

      const response = await fetch(`${API_BASE}/api/auth/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: idToken }),
      });
      if (!response.ok) throw new Error("session-exchange-failed");
      const data: { session_token: string; phone: string } = await response.json();
      setStoredSessionToken(data.session_token);
      setUser({ phone: data.phone });
      setConfirmation(null);
    },
    [confirmation],
  );

  const logout = useCallback(async () => {
    setStoredSessionToken(null);
    setUser(null);
    try {
      if (firebaseConfigured) await signOut(getFirebaseAuth());
    } catch {
      // Already signed out client-side - fine either way.
    }
  }, [firebaseConfigured]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, ready, sendOtp, verifyOtp, logout, firebaseConfigured }),
    [user, ready, sendOtp, verifyOtp, logout, firebaseConfigured],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
