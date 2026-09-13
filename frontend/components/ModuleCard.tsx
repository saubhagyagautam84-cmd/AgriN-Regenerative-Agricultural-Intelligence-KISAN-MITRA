"use client";

/**
 * STEP 4 rendered.
 *
 * One card component for EVERY module, because every module returns the same
 * `ModuleResponse` envelope. Adding a 5th module on the backend needs no
 * change here - only an entry in MODULE_META (optional) and a renderer in
 * ModuleDetails.tsx (also optional; there is a JSON fallback).
 */

import type { ModuleResponse, ModuleStatus } from "@/lib/types";
import ModuleDetails from "./ModuleDetails";
import { useI18n } from "@/lib/i18n/I18nContext";

const MODULE_ICON: Record<string, string> = {
  soil_status: "🧪",
  irrigation_advice: "💧",
  crop_recommendation: "🌾",
  rotation_suggestion: "🔄",
  aggregator: "📋",
  // --- Part B: Regenerative Intelligence Engine ---
  rotation: "🔄",
  soil_health: "🌱",
  fertilizer: "🧪",
  cover_cropping: "🍃",
  irrigation_efficiency: "💧",
};

const STATUS_META: Record<ModuleStatus, { key: string; className: string; icon: string }> = {
  ok: { key: "ok", className: "bg-crop-100 text-crop-700", icon: "✅" },
  partial: {
    key: "partial",
    className: "bg-amber-100 text-amber-900",
    icon: "⚠️",
  },
  error: { key: "error", className: "bg-red-100 text-red-900", icon: "❌" },
};

function titleise(moduleName: string): string {
  return moduleName.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ModuleCard({ response }: { response: ModuleResponse<any> }) {
  const { t } = useI18n();
  const icon = MODULE_ICON[response.module_name] ?? "📦";
  const titleKey = `moduleCard.titles.${response.module_name}`;
  const translatedTitle = t(titleKey);
  const title = translatedTitle === titleKey ? titleise(response.module_name) : translatedTitle;
  const status = STATUS_META[response.status] ?? STATUS_META.error;
  const isDummy = (response.details as { is_dummy_data?: boolean })?.is_dummy_data;

  return (
    <section
      data-testid={`module-card-${response.module_name}`}
      className="flex flex-col rounded-2xl border-2 border-soil-100 bg-surface p-5 shadow-sm"
    >
      {/* ---- envelope: title + status ---- */}
      <header className="flex items-start justify-between gap-3">
        <h3 className="flex items-center gap-3 text-2xl font-bold leading-tight">
          <span aria-hidden className="text-3xl">
            {icon}
          </span>
          <span>{title}</span>
        </h3>
        <span
          className={`shrink-0 rounded-full px-3 py-1 text-sm font-bold ${status.className}`}
          title={`status: ${response.status}`}
        >
          <span aria-hidden>{status.icon}</span> {t(`moduleCard.status.${status.key}`)}
        </span>
      </header>

      {/* ---- envelope: summary (the one line a farmer must read) ---- */}
      <p className="mt-4 text-xl font-semibold leading-snug">{response.summary}</p>

      {/* ---- envelope: confidence (ML modules only) ---- */}
      {response.confidence != null && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-sm font-semibold text-soil-700">
            <span>{t("moduleCard.howSure")}</span>
            <span>{Math.round(response.confidence * 100)}%</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-soil-100">
            <div
              className="h-full rounded-full bg-crop-500"
              style={{ width: `${Math.round(response.confidence * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* ---- module-specific body ---- */}
      <div className="mt-4 flex-1">
        {response.status === "error" ? (
          <p className="text-base text-soil-700">
            {(response.details as { error_message?: string })?.error_message ??
              t("moduleCard.tryAgain")}
          </p>
        ) : (
          <ModuleDetails response={response} />
        )}
      </div>

      {/* ---- envelope: footer ---- */}
      <footer className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-soil-100 pt-3 text-xs text-soil-700">
        <span>
          {/* TODO(ML): this badge disappears on its own once the module sets
              details.is_dummy_data = false. */}
          {isDummy && (
            <span className="mr-2 rounded bg-amber-100 px-2 py-0.5 font-bold text-amber-900">
              {t("moduleCard.demoDataBadge")}
            </span>
          )}
          <code>{response.module_name}</code>
        </span>
        <time dateTime={response.timestamp}>
          {new Date(response.timestamp).toLocaleString("en-IN")}
        </time>
      </footer>
    </section>
  );
}
