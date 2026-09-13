"use client";

/**
 * Part C's Regeneration Score Engine output (backend/regeneration_score/) -
 * the dashboard's headline number, confidence-weighted per module, with the
 * weakest module, a simulated improvement tip, and (once Steps 7/8 land)
 * history and score_drivers.
 */

import type { RegenerationScore } from "@/lib/types";
import { useI18n } from "@/lib/i18n/I18nContext";

const CONFIDENCE_BADGE_CLASS: Record<string, string> = {
  observed: "bg-crop-100 text-crop-700",
  district_avg: "bg-amber-100 text-amber-900",
  estimated: "bg-red-100 text-red-800",
};

function scoreColor(score: number): string {
  if (score >= 70) return "text-crop-600";
  if (score >= 40) return "text-amber-600";
  return "text-red-600";
}

export default function RegenScoreCard({ regen }: { regen: RegenerationScore }) {
  const { t } = useI18n();

  if (regen.score == null || regen.breakdown == null) {
    return (
      <section
        data-testid="regen-score-card"
        className="rounded-2xl border-2 border-soil-200 bg-soil-50 p-5 shadow-sm"
      >
        <h2 className="text-2xl font-bold">{t("regenScore.title")}</h2>
        <p className="mt-3 text-lg text-soil-800">
          {regen.message ?? t("regenScore.insufficientData")}
        </p>
      </section>
    );
  }

  const circumference = 2 * Math.PI * 54;
  const offset = circumference * (1 - regen.score / 100);
  const { _conflicts, ...moduleEntries } = regen.breakdown;

  return (
    <section
      data-testid="regen-score-card"
      className="rounded-2xl border-2 border-crop-200 bg-gradient-to-br from-crop-50 to-white p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-6">
        <div className="relative h-32 w-32 shrink-0">
          <svg viewBox="0 0 120 120" className="h-32 w-32 -rotate-90">
            <circle cx="60" cy="60" r="54" fill="none" stroke="#e7e5e4" strokeWidth="10" />
            <circle
              cx="60"
              cy="60"
              r="54"
              fill="none"
              stroke="currentColor"
              strokeWidth="10"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
              className={scoreColor(regen.score)}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-3xl font-extrabold ${scoreColor(regen.score)}`}>{regen.score}</span>
            <span className="text-xs text-soil-700">/100</span>
          </div>
        </div>

        <div className="flex-1">
          <h2 className="text-2xl font-bold">{t("regenScore.title")}</h2>
          <div className="mt-1 flex flex-wrap gap-2">
            <span
              className={`inline-block rounded-full px-3 py-1 text-sm font-bold ${
                regen.confidence === "High" ? "bg-crop-100 text-crop-700" : "bg-amber-100 text-amber-900"
              }`}
            >
              {regen.confidence === "High" ? t("regenScore.highConfidence") : t("regenScore.estimatedConfidence")}
            </span>
            {regen.score_tone && (
              <span className="inline-block rounded-full bg-soil-100 px-3 py-1 text-sm font-bold text-soil-800 capitalize">
                {regen.score_tone}
              </span>
            )}
          </div>

          <div className="mt-4 space-y-2">
            {Object.entries(moduleEntries).map(([key, entry]) => {
              const badgeClass = CONFIDENCE_BADGE_CLASS[entry.confidence] ?? CONFIDENCE_BADGE_CLASS.estimated;
              const labelKey = `regenScore.moduleLabels.${key}`;
              const translatedLabel = t(labelKey);
              const moduleLabel = translatedLabel === labelKey ? key : translatedLabel;
              return (
                <div key={key}>
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-2">
                      {moduleLabel}
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${badgeClass}`}>
                        {t(`regenScore.confidenceBadge.${entry.confidence}`)}
                      </span>
                    </span>
                    <span className="font-semibold tabular-nums">{entry.score}/100</span>
                  </div>
                  <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-soil-100">
                    <div className="h-full rounded-full bg-crop-500" style={{ width: `${entry.score}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {regen.improvement_tip && (
        <p className="mt-4 rounded-xl bg-crop-50 px-4 py-3 text-base">
          <span aria-hidden>💡 </span>
          {regen.improvement_tip}
        </p>
      )}

      {_conflicts && _conflicts.length > 0 && (
        <div className="mt-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <strong>{t("regenScore.mixedSignals")}</strong>
          <ul className="mt-1 list-inside list-disc">
            {_conflicts.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {regen.history && (
        <p className="mt-3 text-sm text-soil-700">
          <strong>{regen.history.trend}</strong>
        </p>
      )}

      {regen.score_drivers && regen.score_drivers.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-bold text-soil-800">{t("regenScore.scoreDriversTitle")}</h3>
          <ul className="mt-1 space-y-1">
            {regen.score_drivers.map((driver, i) => (
              <li key={i} className="flex justify-between text-sm">
                <span>{driver.factor}</span>
                <span className={driver.impact.startsWith("-") ? "text-red-700" : "text-crop-700"}>
                  {driver.impact}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
