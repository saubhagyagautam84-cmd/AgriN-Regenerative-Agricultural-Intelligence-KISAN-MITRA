"use client";

/**
 * Add family member - real backend-persisted (SQLite, see
 * backend/services/auth.py's family_members table), gated on being logged
 * in (see lib/auth/AuthContext.tsx).
 */

import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n/I18nContext";
import { useAuth } from "@/lib/auth/AuthContext";
import { addFamilyMember, listFamilyMembers, removeFamilyMember, type FamilyMember, ApiError } from "@/lib/api";

export default function FamilyModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      setLoadingList(false);
      return;
    }
    listFamilyMembers()
      .then(setMembers)
      .catch(() => setMembers([]))
      .finally(() => setLoadingList(false));
  }, [user]);

  async function handleAdd() {
    if (!name.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const member = await addFamilyMember(name.trim(), phone.trim() || null);
      setMembers((previous) => [...previous, member]);
      setName("");
      setPhone("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("dashboard.genericError"));
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(id: number) {
    try {
      await removeFamilyMember(id);
      setMembers((previous) => previous.filter((m) => m.id !== id));
    } catch {
      // Leave the list as-is - the user can retry the removal.
    }
  }

  return (
    <div className="modal-backdrop" data-testid="family-modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" data-testid="family-modal" role="dialog" aria-modal="true" aria-label={t("familyModal.title")}>
        <button type="button" className="modal-close float-right border-none bg-none text-xl" style={{ color: "var(--ink-soft)" }} onClick={onClose}>
          ×
        </button>
        <h2>{t("familyModal.title")}</h2>

        {!user ? (
          <p className="helper-note">{t("familyModal.loginFirst")}</p>
        ) : (
          <>
            <p>{t("familyModal.subtitle")}</p>

            {!loadingList && members.length > 0 && (
              <ul className="mb-3 space-y-2" data-testid="family-member-list">
                {members.map((member) => (
                  <li
                    key={member.id}
                    className="flex items-center justify-between rounded-lg px-3 py-2 text-sm"
                    style={{ background: "var(--surface-2)" }}
                  >
                    <span>
                      {member.name}
                      {member.phone ? ` · ${member.phone}` : ""}
                    </span>
                    <button
                      type="button"
                      className="font-semibold text-danger"
                      onClick={() => handleRemove(member.id)}
                    >
                      {t("familyModal.remove")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {!loadingList && members.length === 0 && (
              <p className="mb-3 text-sm text-soil-700">{t("familyModal.listEmpty")}</p>
            )}

            <input
              className="text-input"
              data-testid="family-name-input"
              autoComplete="off"
              placeholder={t("familyModal.namePlaceholder")}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <input
              className="text-input mt-3"
              data-testid="family-phone-input"
              autoComplete="off"
              inputMode="numeric"
              maxLength={10}
              placeholder={t("familyModal.phonePlaceholder")}
              value={phone}
              onChange={(event) => setPhone(event.target.value.replace(/\D/g, ""))}
            />
            {error && <p className="error-text">{error}</p>}
            <button
              type="button"
              data-testid="family-add-button"
              className="btn-primary mt-3 w-full"
              disabled={busy || !name.trim()}
              onClick={handleAdd}
            >
              {busy ? t("familyModal.adding") : t("familyModal.addMember")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
