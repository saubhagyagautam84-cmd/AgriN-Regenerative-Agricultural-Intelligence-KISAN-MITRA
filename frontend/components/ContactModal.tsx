"use client";

/**
 * Contact us - the prototype ships fake helpline/email placeholders
 * ("1800-XXX-XXXX", "help@kisansathi.example"). Real details were not
 * supplied for this build, so this shows an honest pending note instead of
 * inventing something that looks real (see the integration brief's "no
 * silent placeholders" rule) - swap in the real phone/email here once given.
 */

import { useI18n } from "@/lib/i18n/I18nContext";

export default function ContactModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();

  return (
    <div className="modal-backdrop" data-testid="contact-modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" data-testid="contact-modal" role="dialog" aria-modal="true" aria-label={t("contactModal.title")}>
        <button type="button" className="modal-close float-right border-none bg-none text-xl" style={{ color: "var(--ink-soft)" }} onClick={onClose}>
          ×
        </button>
        <h2>{t("contactModal.title")}</h2>
        <p>{t("contactModal.subtitle")}</p>
        <p className="helper-note">{t("contactModal.pendingNote")}</p>
        <button type="button" className="btn-primary w-full" onClick={onClose}>
          {t("contactModal.close")}
        </button>
      </div>
    </div>
  );
}
