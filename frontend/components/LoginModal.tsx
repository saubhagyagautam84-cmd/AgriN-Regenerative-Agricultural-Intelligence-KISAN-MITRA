"use client";

/**
 * Real phone-OTP login modal - see lib/auth/AuthContext.tsx for the
 * Firebase Phone Auth + backend session exchange this drives.
 *
 * If Firebase isn't configured yet (no NEXT_PUBLIC_FIREBASE_* env vars),
 * this says so plainly instead of pretending OTP was sent - per the
 * integration brief's "no silent placeholders" rule.
 */

import { useState } from "react";
import { useI18n } from "@/lib/i18n/I18nContext";
import { useAuth } from "@/lib/auth/AuthContext";

const RECAPTCHA_CONTAINER_ID = "login-recaptcha-container";

type Stage = "phone" | "otp";

export default function LoginModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const { user, sendOtp, verifyOtp, logout, firebaseConfigured } = useAuth();
  const [stage, setStage] = useState<Stage>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSendOtp() {
    setError(null);
    if (!/^[6-9]\d{9}$/.test(phone.trim())) {
      setError(t("loginModal.invalidPhone"));
      return;
    }
    setBusy(true);
    try {
      await sendOtp(`+91${phone.trim()}`, RECAPTCHA_CONTAINER_ID);
      setStage("otp");
    } catch {
      setError(t("dashboard.genericError"));
    } finally {
      setBusy(false);
    }
  }

  async function handleVerify() {
    setError(null);
    setBusy(true);
    try {
      await verifyOtp(code.trim());
      onClose();
    } catch {
      setError(t("loginModal.invalidOtp"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" data-testid="login-modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" data-testid="login-modal" role="dialog" aria-modal="true" aria-label={t("loginModal.title")}>
        <button type="button" className="modal-close float-right border-none bg-none text-xl" style={{ color: "var(--ink-soft)" }} onClick={onClose}>
          ×
        </button>
        <h2>{t("loginModal.title")}</h2>

        {user ? (
          <>
            <p>{t("loginModal.loggedInAs", { phone: user.phone })}</p>
            <button
              type="button"
              className="btn-primary w-full"
              onClick={async () => {
                await logout();
                onClose();
              }}
            >
              {t("loginModal.logout")}
            </button>
          </>
        ) : !firebaseConfigured ? (
          <p className="helper-note">
            Login isn&apos;t configured yet - this app needs a Firebase project&apos;s Web config in
            NEXT_PUBLIC_FIREBASE_* environment variables before it can send a real OTP. The rest of this
            modal, and the backend session endpoints, are fully built and ready once that config is added.
          </p>
        ) : (
          <>
            <p>{t("loginModal.subtitle")}</p>

            {stage === "phone" && (
              <>
                <input
                  className="text-input"
                  data-testid="login-phone-input"
                  inputMode="numeric"
                  autoComplete="tel"
                  maxLength={10}
                  placeholder={t("loginModal.phonePlaceholder")}
                  value={phone}
                  onChange={(event) => setPhone(event.target.value.replace(/\D/g, ""))}
                />
                {error && <p className="error-text">{error}</p>}
                <div id={RECAPTCHA_CONTAINER_ID} />
                <button
                  type="button"
                  data-testid="login-send-otp"
                  className="btn-primary mt-3 w-full"
                  disabled={busy}
                  onClick={handleSendOtp}
                >
                  {busy ? t("loginModal.sending") : t("loginModal.sendOtp")}
                </button>
              </>
            )}

            {stage === "otp" && (
              <>
                <p className="text-sm">{t("loginModal.sentTo", { phone: `+91${phone}` })}</p>
                <input
                  className="text-input"
                  data-testid="login-otp-input"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  placeholder={t("loginModal.otpPlaceholder")}
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                />
                {error && <p className="error-text">{error}</p>}
                <button
                  type="button"
                  data-testid="login-verify-otp"
                  className="btn-primary mt-3 w-full"
                  disabled={busy}
                  onClick={handleVerify}
                >
                  {busy ? t("loginModal.verifying") : t("loginModal.verifyOtp")}
                </button>
                <button
                  type="button"
                  className="mt-2 w-full text-center text-sm font-semibold text-crop-700"
                  onClick={handleSendOtp}
                  disabled={busy}
                >
                  {t("loginModal.resend")}
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
