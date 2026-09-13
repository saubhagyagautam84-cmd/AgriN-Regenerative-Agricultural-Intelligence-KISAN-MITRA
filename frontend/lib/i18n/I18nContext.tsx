"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  DEFAULT_LANGUAGE,
  LANGUAGE_STORAGE_KEY,
  isSupportedLanguage,
  type LanguageCode,
} from "./languages";
import { TRANSLATIONS } from "./translations";

type Vars = Record<string, string | number>;

interface I18nContextValue {
  language: LanguageCode;
  setLanguage: (lang: LanguageCode) => void;
  /** Looks up a dot-path key (e.g. "form.pincode.label"), with {var} interpolation. Falls back to English, then the key itself. */
  t: (key: string, vars?: Vars) => string;
  /** True once we've checked localStorage - lets callers avoid a flash of the picker before we know. */
  ready: boolean;
  /** True if this is the visitor's first time (no stored language choice yet). */
  isFirstVisit: boolean;
  dismissFirstVisit: () => void;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function getByPath(obj: unknown, path: string): string | undefined {
  const value = path.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as object)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, obj);
  return typeof value === "string" ? value : undefined;
}

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, key) => {
    const value = vars[key];
    return value !== undefined ? String(value) : match;
  });
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<LanguageCode>(DEFAULT_LANGUAGE);
  const [ready, setReady] = useState(false);
  const [isFirstVisit, setIsFirstVisit] = useState(false);

  useEffect(() => {
    // Read localStorage only on the client, after mount - avoids an SSR/CSR
    // hydration mismatch (the server always renders the default language).
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    } catch {
      // Private browsing / blocked storage - fall through, treat as first visit.
    }
    if (isSupportedLanguage(stored)) {
      setLanguageState(stored);
      setIsFirstVisit(false);
    } else {
      setIsFirstVisit(true);
    }
    setReady(true);
  }, []);

  const setLanguage = useCallback((lang: LanguageCode) => {
    setLanguageState(lang);
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
    } catch {
      // Best-effort only - the app still works for this session even if storage is blocked.
    }
  }, []);

  const dismissFirstVisit = useCallback(() => setIsFirstVisit(false), []);

  const t = useCallback(
    (key: string, vars?: Vars) => {
      const current = getByPath(TRANSLATIONS[language], key);
      if (current !== undefined) return interpolate(current, vars);
      const fallback = getByPath(TRANSLATIONS[DEFAULT_LANGUAGE], key);
      if (fallback !== undefined) return interpolate(fallback, vars);
      return key;
    },
    [language],
  );

  const value = useMemo<I18nContextValue>(
    () => ({ language, setLanguage, t, ready, isFirstVisit, dismissFirstVisit }),
    [language, setLanguage, t, ready, isFirstVisit, dismissFirstVisit],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
