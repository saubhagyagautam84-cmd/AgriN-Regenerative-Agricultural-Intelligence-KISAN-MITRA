"use client";

/**
 * The 3-dot menu, ported from kisan-sathi-frontend.html: Login, Day/night
 * mode, Change language, Add family member, Contact us.
 *
 * Two real bug-fix patterns are carried over verbatim from the prototype
 * (see globals.css's `[hidden]` rule and MASTER PROMPT STEP 5/6):
 *   - the panel and modals use the `hidden` attribute, not a manual
 *     `display` toggle, so a closed panel never keeps capturing clicks.
 *   - closing a modal clears its own state rather than clobbering a
 *     shared innerHTML blob another part of the page depends on.
 */

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n/I18nContext";
import { useTheme } from "@/lib/theme/ThemeContext";
import { SUPPORTED_LANGUAGES, type LanguageCode } from "@/lib/i18n/languages";
import LoginModal from "@/components/LoginModal";
import FamilyModal from "@/components/FamilyModal";
import ContactModal from "@/components/ContactModal";
import { useAuth } from "@/lib/auth/AuthContext";

type ActiveModal = "login" | "family" | "contact" | null;

interface Props {
  /** Resets the app back to a fresh wizard start (see page.tsx's goHome). */
  onHome: () => void;
  /** Jumps to the last submitted results, or nudges the farmer to submit the form first (see page.tsx's goToMyReport). */
  onMyReport: () => void;
}

export default function MoreMenu({ onHome, onMyReport }: Props) {
  const { t, language, setLanguage } = useI18n();
  const { toggleTheme } = useTheme();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState<ActiveModal>(null);
  const [langOpen, setLangOpen] = useState(false);
  // Panel is `fixed` and anchored to the true viewport edge (not the
  // button's own position) - on narrow phones the 3-dot button isn't flush
  // against the screen edge (the "Load demo farm" button sits after it in
  // the header), so anchoring to the button clipped the panel off-screen to
  // the left. See tests/wizard_check.spec.ts's responsive assertions.
  const [panelTop, setPanelTop] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
        setLangOpen(false);
      }
    }
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  function toggleOpen(event: React.MouseEvent) {
    event.stopPropagation();
    if (!open && buttonRef.current) {
      setPanelTop(buttonRef.current.getBoundingClientRect().bottom + 6);
    }
    setOpen((previous) => !previous);
    setLangOpen(false);
  }

  return (
    <div className="menu-wrap relative" ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        className="icon-btn"
        data-testid="more-menu-button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={t("menu.moreOptions")}
        onClick={toggleOpen}
      >
        ⋮
      </button>

      <div
        className="menu-panel fixed right-4 z-50 min-w-[220px] max-w-[calc(100vw-2rem)] rounded-xl border p-1.5"
        style={{ top: panelTop, background: "var(--surface)", borderColor: "var(--line)", boxShadow: "0 8px 24px rgba(32,48,31,0.14)" }}
        data-testid="more-menu-panel"
        hidden={!open}
      >
        <button
          type="button"
          data-testid="menu-home"
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-base"
          style={{ color: "var(--ink)" }}
          onClick={() => {
            setOpen(false);
            onHome();
          }}
        >
          🏠 {t("menu.home")}
        </button>
        <button
          type="button"
          data-testid="menu-login"
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-base"
          style={{ color: "var(--ink)" }}
          onClick={() => {
            setOpen(false);
            setModal("login");
          }}
        >
          👤 {user ? t("loginModal.loggedInAs", { phone: user.phone }) : t("menu.login")}
        </button>
        <button
          type="button"
          data-testid="menu-theme"
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-base"
          style={{ color: "var(--ink)" }}
          onClick={() => {
            setOpen(false);
            toggleTheme();
          }}
        >
          🌗 {t("menu.theme")}
        </button>

        <div className="relative">
          <button
            type="button"
            data-testid="menu-language"
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-base"
            style={{ color: "var(--ink)" }}
            onClick={(event) => {
              event.stopPropagation();
              setLangOpen((previous) => !previous);
            }}
          >
            🌐 {t("menu.changeLanguage")}
          </button>
          {langOpen && (
            <div
              className="ml-2 mt-1 max-h-56 overflow-y-auto rounded-lg border p-1"
              style={{ background: "var(--surface-2)", borderColor: "var(--line)" }}
            >
              {SUPPORTED_LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  type="button"
                  data-testid={`menu-language-${lang.code}`}
                  className={`block w-full rounded-md px-2.5 py-1.5 text-left text-sm ${
                    language === lang.code ? "font-bold" : ""
                  }`}
                  style={{ color: language === lang.code ? "var(--green-900)" : "var(--ink)" }}
                  onClick={() => {
                    setLanguage(lang.code as LanguageCode);
                    setLangOpen(false);
                    setOpen(false);
                  }}
                >
                  {lang.nativeName}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="my-1 h-px" style={{ background: "var(--line)" }} />

        <button
          type="button"
          data-testid="menu-add-family"
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-base"
          style={{ color: "var(--ink)" }}
          onClick={() => {
            setOpen(false);
            setModal("family");
          }}
        >
          ➕ {t("menu.addFamily")}
        </button>
        <button
          type="button"
          data-testid="menu-contact"
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-base"
          style={{ color: "var(--ink)" }}
          onClick={() => {
            setOpen(false);
            setModal("contact");
          }}
        >
          ☎️ {t("menu.contact")}
        </button>
        <button
          type="button"
          data-testid="menu-my-report"
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-base"
          style={{ color: "var(--ink)" }}
          onClick={() => {
            setOpen(false);
            onMyReport();
          }}
        >
          📋 {t("menu.myReport")}
        </button>
      </div>

      {modal === "login" && <LoginModal onClose={() => setModal(null)} />}
      {modal === "family" && <FamilyModal onClose={() => setModal(null)} />}
      {modal === "contact" && <ContactModal onClose={() => setModal(null)} />}
    </div>
  );
}
