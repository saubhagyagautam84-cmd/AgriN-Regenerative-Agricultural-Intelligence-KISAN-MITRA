"use client";

/**
 * The Regeneration Score Engine's headline number - a weighted sum of the
 * five module sub-scores, with the confidence label and per-field
 * data_confidence breakdown the Feature Resolver produced.
 */

import type { RegenerationScore } from "@/lib/types";

const SUB_SCORE_LABELS: Record<string, string> = {
  carbon_trend_score: "Soil carbon (M2)",
  fertilizer_efficiency: "Fertiliser efficiency (M3)",
  rotation_health: "Rotation health (M1)",
  cover_crop_diversity: "Cover-crop diversity (M4)",
  water_efficiency: "Water efficiency (M5)",
};

function scoreColor(score: number): string {
  if (score >= 70) return "text-crop-600";
  if (score >= 40) return "text-amber-600";
  return "text-red-600";
}

export default function RegenScoreCard({ regen }: { regen: RegenerationScore }) {
  const circumference = 2 * Math.PI * 54;
  const offset = circumference * (1 - regen.score / 100);

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
          <h2 className="text-2xl font-bold">
            Regeneration Score
            <span className="block text-sm font-normal text-soil-700">पुनर्जनन स्कोर</span>
          </h2>
          <span
            className={`mt-1 inline-block rounded-full px-3 py-1 text-sm font-bold ${
              regen.confidence === "High" ? "bg-crop-100 text-crop-700" : "bg-amber-100 text-amber-900"
            }`}
          >
            {regen.confidence === "High" ? "✅ High confidence" : "⚠️ Estimated (add a soil test to improve)"}
          </span>

          <div className="mt-4 space-y-2">
            {Object.entries(regen.breakdown.sub_scores).map(([key, value]) => (
              <div key={key}>
                <div className="flex justify-between text-sm">
                  <span>{SUB_SCORE_LABELS[key] ?? key}</span>
                  <span className="font-semibold tabular-nums">{value}/100</span>
                </div>
                <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-soil-100">
                  <div className="h-full rounded-full bg-crop-500" style={{ width: `${value}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-semibold text-soil-700">
          Data confidence per field / डेटा भरोसा
        </summary>
        <div className="mt-2 flex flex-wrap gap-2">
          {Object.entries(regen.breakdown.data_confidence).map(([field, confidence]) => (
            <span
              key={field}
              className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                confidence === "observed" ? "bg-crop-100 text-crop-700" : "bg-amber-100 text-amber-900"
              }`}
            >
              {field.replace(/_/g, " ")}: {confidence}
            </span>
          ))}
        </div>
      </details>
    </section>
  );
}
