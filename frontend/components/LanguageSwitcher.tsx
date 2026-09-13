"use client";

/**
 * Persistent way to change language after the first-visit popup is gone -
 * good UX practice (a one-time popup shouldn't be the only way to change
 * your mind), lives in the page header.
 */

import { useI18n } from "@/lib/i18n/I18nContext";
import { SUPPORTED_LANGUAGES, type LanguageCode } from "@/lib/i18n/languages";

export default function LanguageSwitcher() {
  const { language, setLanguage, t } = useI18n();

  return (
    <label className="flex items-center gap-1.5 text-sm font-semibold text-soil-700">
      <span aria-hidden>🌐</span>
      <span className="sr-only">{t("header.changeLanguage")}</span>
      <select
        data-testid="language-switcher"
        value={language}
        onChange={(event) => setLanguage(event.target.value as LanguageCode)}
        className="touch-target rounded-lg border-2 border-soil-100 bg-surface px-2 py-1 text-sm font-semibold text-soil-900"
        aria-label={t("header.changeLanguage")}
      >
        {SUPPORTED_LANGUAGES.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.nativeName}
          </option>
        ))}
      </select>
    </label>
  );
}
