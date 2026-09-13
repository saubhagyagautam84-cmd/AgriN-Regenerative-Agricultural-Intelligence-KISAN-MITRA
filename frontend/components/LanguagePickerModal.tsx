"use client";

/**
 * Shown once, on first visit (gated by localStorage via I18nContext's
 * isFirstVisit) - lets the farmer pick a language before seeing anything
 * else. Language can always be changed later via LanguageSwitcher in the
 * header, so this is a convenience, not a one-way gate.
 */

import { useI18n } from "@/lib/i18n/I18nContext";
import { SUPPORTED_LANGUAGES, type LanguageCode } from "@/lib/i18n/languages";

export default function LanguagePickerModal() {
  const { ready, isFirstVisit, setLanguage, dismissFirstVisit, t } = useI18n();

  if (!ready || !isFirstVisit) return null;

  function choose(code: LanguageCode) {
    setLanguage(code);
    dismissFirstVisit();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Choose your language"
    >
      <div className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-xl">
        <h2 className="text-2xl font-bold text-soil-900">{t("languagePicker.title")}</h2>
        <p className="mt-1 text-sm text-soil-700">{t("languagePicker.subtitle")}</p>

        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {SUPPORTED_LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              type="button"
              data-testid={`language-option-${lang.code}`}
              onClick={() => choose(lang.code)}
              className="touch-target rounded-xl border-2 border-soil-100 bg-soil-50 px-3 py-4 text-center font-semibold text-soil-900 transition hover:border-crop-500 hover:bg-crop-50"
            >
              <span className="block text-lg">{lang.nativeName}</span>
              {lang.nativeName !== lang.name && (
                <span className="mt-0.5 block text-xs font-normal text-soil-600">{lang.name}</span>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
