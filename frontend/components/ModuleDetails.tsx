"use client";

/**
 * Per-module renderers for `ModuleResponse.details`.
 *
 * The envelope (title, status, summary, confidence, timestamp) is drawn by
 * ModuleCard for every module identically. Only this file knows what a
 * particular module's `details` object contains.
 *
 * TODO(ML): when a real model replaces a dummy module, these renderers keep
 * working as long as the `details` keys documented in lib/types.ts survive.
 * New keys can simply be added below.
 */

import type {
  CropRecommendationDetails,
  IrrigationDetails,
  ModuleResponse,
  NutrientReading,
  RegenCoverCroppingDetails,
  RegenFertilizerDetails,
  RegenIrrigationDetails,
  RegenRotationDetails,
  RegenSoilHealthDetails,
  RotationDetails,
  SoilStatusDetails,
} from "@/lib/types";

// --------------------------------------------------------------------------
// Shared bits
// --------------------------------------------------------------------------

export function ActionList({ actions }: { actions: string[] }) {
  if (!actions?.length) return null;
  return (
    <div className="mt-5 rounded-xl bg-crop-50 p-4">
      <h4 className="text-base font-bold text-crop-700">
        What to do / क्या करें
      </h4>
      <ul className="mt-2 space-y-2">
        {actions.map((action, index) => (
          <li key={index} className="flex gap-2 text-lg leading-snug">
            <span aria-hidden className="text-crop-600">
              ✔
            </span>
            <span>{action}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value, unit }: { label: string; value: string | number; unit?: string }) {
  return (
    <div className="rounded-xl bg-soil-50 px-3 py-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-soil-700">{label}</div>
      <div className="text-xl font-bold">
        {value}
        {unit && <span className="ml-1 text-sm font-medium text-soil-700">{unit}</span>}
      </div>
    </div>
  );
}

const RATING_STYLES: Record<string, { bar: string; chip: string; label: string }> = {
  low: { bar: "bg-red-500", chip: "bg-red-100 text-red-800", label: "Low" },
  medium: { bar: "bg-amber-500", chip: "bg-amber-100 text-amber-900", label: "OK" },
  high: { bar: "bg-crop-500", chip: "bg-crop-100 text-crop-700", label: "High" },
};

function NutrientRow({ nutrient }: { nutrient: NutrientReading }) {
  const rating = nutrient.rating ?? "medium";
  const style = RATING_STYLES[rating] ?? RATING_STYLES.medium;

  // Position the bar across low -> high using the rating band edges.
  const scaleMax = nutrient.high_above * 1.6;
  const percent = Math.max(4, Math.min(100, (nutrient.value / scaleMax) * 100));

  return (
    <li className="py-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-lg font-semibold">{nutrient.label}</span>
        <span className="text-base tabular-nums text-soil-700">
          {nutrient.value} {nutrient.unit}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-3">
        <div className="h-3 flex-1 overflow-hidden rounded-full bg-soil-100">
          <div className={`h-full rounded-full ${style.bar}`} style={{ width: `${percent}%` }} />
        </div>
        <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${style.chip}`}>
          {style.label}
          {nutrient.rating_hi ? ` / ${nutrient.rating_hi}` : ""}
        </span>
      </div>
    </li>
  );
}

// --------------------------------------------------------------------------
// 1. Soil status
// --------------------------------------------------------------------------

function SoilStatusView({ details }: { details: SoilStatusDetails }) {
  const plan = details.fertiliser_plan;

  return (
    <>
      {details.sample && (
        <p className="mb-3 text-sm text-soil-700">
          Sample: {details.sample.soil_type ?? "soil"} from{" "}
          {details.sample.village ?? details.sample.district ?? "your area"}
          {details.sample.test_date ? `, tested ${details.sample.test_date}` : ""}
          {details.sample.records_averaged > 1
            ? ` (average of ${details.sample.records_averaged} samples)`
            : ""}
        </p>
      )}

      {details.nutrients.length > 0 && (
        <ul className="divide-y divide-soil-100">
          {details.nutrients.map((nutrient) => (
            <NutrientRow key={nutrient.key} nutrient={nutrient} />
          ))}
        </ul>
      )}

      <div className="mt-4 grid grid-cols-2 gap-2">
        {details.ph?.value != null && <Stat label="Soil pH" value={details.ph.value} />}
        {details.ec?.value != null && (
          <Stat label="Salt (EC)" value={details.ec.value} unit="dS/m" />
        )}
      </div>
      {details.ph?.text && <p className="mt-2 text-base text-soil-700">{details.ph.text}.</p>}

      {plan && (
        <div className="mt-5 rounded-xl border-2 border-soil-100 p-4">
          <h4 className="text-base font-bold">
            Fertiliser for your field / खाद
            <span className="ml-2 text-sm font-normal text-soil-700">
              ({plan.for_your_field.area_hectare} ha)
            </span>
          </h4>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <Stat label="Urea" value={plan.for_your_field.urea_bags_45kg} unit="bags" />
            <Stat label="DAP" value={plan.for_your_field.dap_bags_50kg} unit="bags" />
            <Stat label="MOP" value={plan.for_your_field.mop_bags_50kg} unit="bags" />
          </div>
          <p className="mt-3 text-sm text-soil-700">{plan.note}</p>
        </div>
      )}

      <ActionList actions={details.farmer_actions} />
    </>
  );
}

// --------------------------------------------------------------------------
// 2. Irrigation
// --------------------------------------------------------------------------

const IRRIGATION_BANNER: Record<string, { text: string; className: string; icon: string }> = {
  irrigate_now: { text: "Irrigate today", className: "bg-red-100 text-red-900", icon: "🚨" },
  irrigate_soon: { text: "Irrigate in ~2 days", className: "bg-amber-100 text-amber-900", icon: "⏳" },
  wait: { text: "Wait — rain is coming", className: "bg-blue-100 text-blue-900", icon: "🌧️" },
  none: { text: "No irrigation needed", className: "bg-crop-100 text-crop-700", icon: "✅" },
  conserve: { text: "Save the moisture you have", className: "bg-amber-100 text-amber-900", icon: "🍂" },
  pre_sowing: { text: "Prepare moisture before sowing", className: "bg-blue-100 text-blue-900", icon: "🌱" },
  stop: { text: "Stop irrigating", className: "bg-soil-100 text-soil-900", icon: "🛑" },
  unknown: { text: "Not available", className: "bg-soil-100 text-soil-900", icon: "❔" },
};

function IrrigationView({ details }: { details: IrrigationDetails }) {
  const banner = IRRIGATION_BANNER[details.action] ?? IRRIGATION_BANNER.unknown;
  const balance = details.water_balance;

  return (
    <>
      <div className={`flex items-center gap-3 rounded-xl px-4 py-3 ${banner.className}`}>
        <span className="text-3xl" aria-hidden>
          {banner.icon}
        </span>
        <span className="text-xl font-bold">{banner.text}</span>
      </div>

      {details.depth_mm != null && details.depth_mm > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <Stat label="Water depth" value={details.depth_mm} unit="mm" />
          <Stat
            label="For your field"
            value={(details.water_litres ?? 0).toLocaleString("en-IN")}
            unit="litres"
          />
        </div>
      )}

      {balance && (
        <div className="mt-4">
          <h4 className="text-base font-bold">This week&apos;s water balance</h4>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Stat label="Crop needs" value={balance.demand_next_7d_mm} unit="mm" />
            <Stat label="Rain (past 7d)" value={balance.rain_last_7d_mm} unit="mm" />
            <Stat label="Rain (next 7d)" value={balance.rain_forecast_7d_mm} unit="mm" />
          </div>
        </div>
      )}

      {details.next_critical_stage && (
        <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-lg">
          <strong>Next key stage:</strong> {details.next_critical_stage.stage} in{" "}
          {details.next_critical_stage.days_from_today} days.
          {details.next_critical_stage.note ? ` ${details.next_critical_stage.note}.` : ""}
        </p>
      )}

      {details.forecast && details.forecast.length > 0 && (
        <div className="mt-4">
          <h4 className="text-base font-bold">Next 5 days</h4>
          <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
            {details.forecast.map((day) => (
              <div
                key={day.date}
                className="min-w-[5.5rem] flex-1 rounded-xl bg-soil-50 px-2 py-2 text-center"
              >
                <div className="text-xs font-semibold text-soil-700">
                  {new Date(day.date).toLocaleDateString("en-IN", {
                    weekday: "short",
                  })}
                </div>
                <div className="text-2xl" aria-hidden>
                  {day.rain_mm >= 7.5 ? "🌧️" : day.rain_mm > 0 ? "🌦️" : "☀️"}
                </div>
                <div className="text-sm font-bold">{day.rain_mm} mm</div>
                <div className="text-xs text-soil-700">{Math.round(day.temp_max_c)}°C</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <ActionList actions={details.farmer_actions} />
    </>
  );
}

// --------------------------------------------------------------------------
// 3. Crop recommendation
// --------------------------------------------------------------------------

function CropRecommendationView({ details }: { details: CropRecommendationDetails }) {
  return (
    <>
      {details.season_window && (
        <p className="mb-3 text-base text-soil-700">
          Planning for <strong>{details.season_window}</strong>
          {details.after_crop ? `, after your ${details.after_crop}` : ""}.
        </p>
      )}

      <ol className="space-y-3">
        {details.recommendations.map((crop, index) => (
          <li
            key={crop.crop_name}
            className={`rounded-xl border-2 p-4 ${
              index === 0 ? "border-crop-500 bg-crop-50" : "border-soil-100 bg-white"
            }`}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xl font-bold">
                {index === 0 && <span aria-hidden>⭐ </span>}
                {crop.crop_name}
                {crop.local_name && (
                  <span className="ml-2 text-base font-normal text-soil-700">
                    {crop.local_name}
                  </span>
                )}
              </span>
              <span className="text-base font-bold tabular-nums">{crop.score}/100</span>
            </div>

            <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-soil-100">
              <div
                className={`h-full rounded-full ${index === 0 ? "bg-crop-500" : "bg-soil-700/40"}`}
                style={{ width: `${crop.score}%` }}
              />
            </div>

            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-soil-700">
              <span>💧 {crop.water_requirement_mm} mm</span>
              <span>📅 {crop.duration_days} days</span>
              {crop.is_legume && <span>🌱 adds nitrogen</span>}
            </div>

            {crop.reasons.length > 0 && (
              <ul className="mt-2 space-y-1">
                {crop.reasons.map((reason, reasonIndex) => (
                  <li key={reasonIndex} className="text-base">
                    <span aria-hidden className="text-crop-600">
                      ✔{" "}
                    </span>
                    {reason}
                  </li>
                ))}
              </ul>
            )}
            {crop.warnings.length > 0 && (
              <ul className="mt-1 space-y-1">
                {crop.warnings.map((warning, warningIndex) => (
                  <li key={warningIndex} className="text-base text-amber-800">
                    <span aria-hidden>⚠️ </span>
                    {warning}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>

      <ActionList actions={details.farmer_actions} />
    </>
  );
}

// --------------------------------------------------------------------------
// 4. Rotation
// --------------------------------------------------------------------------

function RotationView({ details }: { details: RotationDetails }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-soil-100 px-3 py-1 text-base font-semibold">
          Now: {details.current_crop}
          {details.current_crop_local_name ? ` / ${details.current_crop_local_name}` : ""}
        </span>
      </div>

      <ol className="mt-4 space-y-3">
        {details.plan.map((step) => (
          <li key={step.sequence} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-crop-600 text-base font-bold text-white">
                {step.sequence}
              </span>
              <span className="mt-1 w-0.5 flex-1 bg-soil-100" aria-hidden />
            </div>
            <div className="flex-1 pb-1">
              <div className="text-xl font-bold">
                {step.crop_name}
                {step.local_name && (
                  <span className="ml-2 text-base font-normal text-soil-700">
                    {step.local_name}
                  </span>
                )}
                {step.is_legume && <span className="ml-2 text-base">🌱</span>}
              </div>
              <div className="text-sm font-semibold text-soil-700">{step.window}</div>
              <p className="mt-1 text-base">{step.reason}</p>
            </div>
          </li>
        ))}
      </ol>

      {details.avoid.length > 0 && (
        <p className="mt-3 rounded-xl bg-red-50 px-4 py-3 text-lg text-red-900">
          <strong>Do not sow after {details.current_crop}:</strong> {details.avoid.join(", ")}
        </p>
      )}

      <ActionList actions={details.farmer_actions} />
    </>
  );
}

// --------------------------------------------------------------------------
// PART B - Regenerative Intelligence Engine
// --------------------------------------------------------------------------

function RegenRotationView({ details }: { details: RegenRotationDetails }) {
  return (
    <>
      <p className="mb-3 text-base text-soil-700">{details.reason}</p>
      <ol className="space-y-3">
        {details.next_crop_suggestions.map((crop, index) => (
          <li
            key={crop.crop_name}
            className={`rounded-xl border-2 p-4 ${
              index === 0 ? "border-crop-500 bg-crop-50" : "border-soil-100 bg-white"
            }`}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xl font-bold">
                {index === 0 && <span aria-hidden>⭐ </span>}
                {crop.crop_name}
                {crop.local_name && (
                  <span className="ml-2 text-base font-normal text-soil-700">{crop.local_name}</span>
                )}
                {crop.is_legume && <span className="ml-2 text-base">🌱</span>}
              </span>
              <span className="text-base font-bold tabular-nums">{crop.score}/100</span>
            </div>
            <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-soil-100">
              <div
                className={`h-full rounded-full ${index === 0 ? "bg-crop-500" : "bg-soil-700/40"}`}
                style={{ width: `${crop.score}%` }}
              />
            </div>
            {crop.reasons.length > 0 && (
              <ul className="mt-2 space-y-1">
                {crop.reasons.map((reason, reasonIndex) => (
                  <li key={reasonIndex} className="text-base">
                    <span aria-hidden className="text-crop-600">✔ </span>
                    {reason}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
      {details.avoid && details.avoid.length > 0 && (
        <p className="mt-3 rounded-xl bg-red-50 px-4 py-3 text-lg text-red-900">
          <strong>Avoid next:</strong> {details.avoid.join(", ")}
        </p>
      )}
    </>
  );
}

const SEVERITY_STYLE: Record<string, { className: string; label: string }> = {
  low: { className: "bg-crop-100 text-crop-700", label: "Low depletion" },
  moderate: { className: "bg-amber-100 text-amber-900", label: "Moderate depletion" },
  severe: { className: "bg-red-100 text-red-900", label: "Severe depletion" },
};

function SoilHealthView({ details }: { details: RegenSoilHealthDetails }) {
  const severity = SEVERITY_STYLE[details.severity] ?? SEVERITY_STYLE.moderate;
  const allPoints = [
    ...details.projection.current_practice.map((p) => p.soil_health_score),
    ...details.projection.regenerative_practice.map((p) => p.soil_health_score),
    details.soil_health_score,
  ];
  const maxScore = Math.max(100, ...allPoints);

  return (
    <>
      <div className="flex items-center gap-3">
        <span className="text-4xl font-extrabold tabular-nums">{details.soil_health_score}</span>
        <span className="text-lg text-soil-700">/100</span>
        <span className={`ml-auto rounded-full px-3 py-1 text-sm font-bold ${severity.className}`}>
          {severity.label}
        </span>
      </div>

      <div className="mt-4">
        <h4 className="text-base font-bold">3-season projection</h4>
        <p className="mt-1 text-sm text-soil-700">{details.trend}</p>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {[0, 1, 2].map((i) => {
            const current = details.projection.current_practice[i];
            const regen = details.projection.regenerative_practice[i];
            return (
              <div key={i} className="rounded-xl bg-soil-50 p-2 text-center">
                <div className="text-xs font-semibold text-soil-700">Season {current.season}</div>
                <div className="mt-1 flex flex-col gap-1">
                  <div className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-red-500" aria-hidden />
                    <span className="text-sm font-bold tabular-nums">{current.soil_health_score}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-crop-600" aria-hidden />
                    <span className="text-sm font-bold tabular-nums">{regen.soil_health_score}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-2 flex gap-4 text-xs text-soil-700">
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-red-500" aria-hidden />Current practice</span>
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-crop-600" aria-hidden />Regenerative practice</span>
        </div>
      </div>

      <p className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-base">{details.flag}</p>
    </>
  );
}

function FertilizerView({ details }: { details: RegenFertilizerDetails }) {
  if (!details.recommended_npk || !details.current_estimated_usage) {
    return <p className="text-base text-soil-700">No fertiliser model output available.</p>;
  }
  const rec = details.recommended_npk;
  const cur = details.current_estimated_usage;

  return (
    <>
      <div className="grid grid-cols-3 gap-2 text-center">
        {(["N", "P", "K"] as const).map((nutrient) => {
          const recKey = `${nutrient}_kg_per_ha` as keyof typeof rec;
          const curKey = `${nutrient}_kg_per_ha` as keyof typeof cur;
          return (
            <div key={nutrient} className="rounded-xl bg-soil-50 p-2">
              <div className="text-xs font-semibold uppercase text-soil-700">{nutrient}</div>
              <div className="text-lg font-bold text-crop-700">{rec[recKey]} kg/ha</div>
              <div className="text-xs text-soil-700 line-through">{cur[curKey]} kg/ha typical</div>
            </div>
          );
        })}
      </div>

      {details.reduction_percent != null && (
        <p className="mt-3 text-lg font-semibold">
          {details.reduction_percent >= 0
            ? `About ${details.reduction_percent}% less total fertiliser than typical usage.`
            : `About ${Math.abs(details.reduction_percent)}% more balanced fertiliser needed (some nutrients under-applied).`}
        </p>
      )}

      {details.explanation.length > 0 && (
        <div className="mt-4">
          <h4 className="text-base font-bold">Why this recommendation / क्यों</h4>
          <ul className="mt-2 space-y-2">
            {details.explanation.map((entry) => (
              <li key={entry.feature}>
                <div className="flex justify-between text-sm">
                  <span>{entry.feature.replace(/_/g, " ")}</span>
                  <span className="font-bold">{entry.contribution_pct}%</span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-soil-100">
                  <div className="h-full rounded-full bg-crop-500" style={{ width: `${entry.contribution_pct}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ActionList actions={details.farmer_actions ?? []} />
    </>
  );
}

const FIXER_LABEL: Record<string, { text: string; className: string }> = {
  fast: { text: "Fast N-fixer", className: "bg-crop-100 text-crop-700" },
  medium: { text: "Some N-fixing", className: "bg-amber-100 text-amber-900" },
  none: { text: "Companion crop", className: "bg-soil-100 text-soil-900" },
  unknown: { text: "Unknown", className: "bg-soil-100 text-soil-900" },
};

function CoverCroppingView({ details }: { details: RegenCoverCroppingDetails }) {
  return (
    <>
      <ol className="space-y-2">
        {details.cover_crop_suggestions.map((suggestion) => {
          const style = FIXER_LABEL[suggestion.nitrogen_fixing_speed] ?? FIXER_LABEL.unknown;
          return (
            <li
              key={suggestion.cover_crop}
              className={`flex items-center justify-between rounded-xl border-2 p-3 ${
                suggestion.rank === 1 ? "border-crop-500 bg-crop-50" : "border-soil-100 bg-white"
              }`}
            >
              <span className="text-lg font-bold">
                {suggestion.rank === 1 && <span aria-hidden>⭐ </span>}
                {suggestion.cover_crop}
              </span>
              <span className={`rounded-full px-3 py-1 text-xs font-bold ${style.className}`}>{style.text}</span>
            </li>
          );
        })}
      </ol>
      {details.benefit && <p className="mt-3 text-base text-soil-700">{details.benefit}</p>}
    </>
  );
}

function IrrigationEfficiencyView({ details }: { details: RegenIrrigationDetails }) {
  return (
    <>
      {details.next_irrigation_date ? (
        <div className="flex items-center gap-3 rounded-xl bg-blue-50 px-4 py-3 text-blue-900">
          <span className="text-3xl" aria-hidden>📅</span>
          <div>
            <div className="text-lg font-bold">Next irrigation: {details.next_irrigation_date}</div>
            {details.water_volume_mm != null && (
              <div className="text-sm">{details.water_volume_mm} mm</div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3 rounded-xl bg-crop-100 px-4 py-3 text-crop-700">
          <span className="text-3xl" aria-hidden>🌧️</span>
          <span className="text-lg font-bold">Rainfall-based - no pump schedule</span>
        </div>
      )}

      <p className="mt-3 text-base">{details.note}</p>

      <div className="mt-4 rounded-xl border-2 border-soil-100 p-4">
        <h4 className="text-base font-bold">Cumulative water saved this season</h4>
        <p className="mt-1 text-2xl font-extrabold text-crop-700">
          {details.cumulative_water_saved_liters.toLocaleString("en-IN")} L
        </p>
        <p className="text-xs text-soil-700">vs. a naive fixed weekly-irrigation schedule</p>
      </div>
    </>
  );
}

// --------------------------------------------------------------------------
// Dispatcher
// --------------------------------------------------------------------------

/**
 * Pick a renderer by module_name. An unknown module still renders - it falls
 * back to a JSON dump - so a new backend module is visible on the dashboard
 * before anyone writes a view for it.
 */
export default function ModuleDetails({ response }: { response: ModuleResponse }) {
  const details = response.details as unknown;

  switch (response.module_name) {
    case "soil_status":
      return <SoilStatusView details={details as SoilStatusDetails} />;
    case "irrigation_advice":
      return <IrrigationView details={details as IrrigationDetails} />;
    case "crop_recommendation":
      return <CropRecommendationView details={details as CropRecommendationDetails} />;
    case "rotation_suggestion":
      return <RotationView details={details as RotationDetails} />;
    case "rotation":
      return <RegenRotationView details={details as RegenRotationDetails} />;
    case "soil_health":
      return <SoilHealthView details={details as RegenSoilHealthDetails} />;
    case "fertilizer":
      return <FertilizerView details={details as RegenFertilizerDetails} />;
    case "cover_cropping":
      return <CoverCroppingView details={details as RegenCoverCroppingDetails} />;
    case "irrigation_efficiency":
      return <IrrigationEfficiencyView details={details as RegenIrrigationDetails} />;
    default:
      return (
        <details className="mt-2">
          <summary className="cursor-pointer text-base font-semibold text-soil-700">
            No view written for &quot;{response.module_name}&quot; yet — raw data
          </summary>
          <pre className="mt-2 overflow-x-auto rounded-xl bg-soil-100 p-3 text-xs">
            {JSON.stringify(response.details, null, 2)}
          </pre>
        </details>
      );
  }
}
