"use client";

/**
 * The strip at the top of the dashboard, built from `/api/aggregate`.
 *
 * It exists to make the STEP 3 aggregation visible: the farmer typed a PIN
 * code and a crop name, and the system resolved a district, a soil sample,
 * weather and an ICAR crop profile from that. It also surfaces the honest
 * `warnings` / `data_gaps` instead of hiding them.
 */

import type { AggregatedData, ModuleResponse } from "@/lib/types";

const STAGE_LABELS: Record<string, string> = {
  not_sown_yet: "Not sown yet",
  establishment: "Just established",
  vegetative: "Growing (vegetative)",
  flowering: "Flowering",
  grain_filling: "Filling grain",
  maturity: "Near harvest",
  past_harvest: "Past harvest",
  unknown: "Unknown stage",
};

function Tile({
  icon,
  label,
  value,
  sub,
}: {
  icon: string;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl bg-white/70 px-3 py-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-soil-700">
        <span aria-hidden className="mr-1">
          {icon}
        </span>
        {label}
      </div>
      <div className="text-lg font-bold leading-tight">{value}</div>
      {sub && <div className="text-xs text-soil-700">{sub}</div>}
    </div>
  );
}

export default function FarmSummary({
  response,
}: {
  response: ModuleResponse<AggregatedData>;
}) {
  const data = response.details;
  const { location, soil, weather, crop_reference: crop, farm_input: input } = data;

  const place =
    [location.village, location.district, location.state].filter(Boolean).join(", ") ||
    `PIN ${location.pincode}`;

  const soilLabel = soil
    ? soil.match_level === "exact_pincode"
      ? "Your area's soil card"
      : `${soil.match_level.replace("_", " ")} average`
    : "Not found";

  return (
    <section className="rounded-2xl border-2 border-crop-500/40 bg-crop-50 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-2xl font-bold">
          {input.farmer_name ? `${input.farmer_name}'s farm` : "Your farm"}
          <span className="block text-sm font-normal text-soil-700">आपका खेत</span>
        </h2>
        <span className="text-sm font-semibold text-soil-700">
          Data found: {Math.round(data.completeness * 100)}%
        </span>
      </div>

      <p className="mt-2 text-lg">{response.summary}</p>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <Tile icon="📍" label="Location" value={place} sub={`PIN ${location.pincode}`} />
        <Tile
          icon="🌾"
          label="Crop"
          value={crop?.crop_name ?? input.crop_name}
          sub={crop?.local_names?.hi ?? undefined}
        />
        <Tile
          icon="📐"
          label="Land"
          value={`${input.land_size} ${input.land_unit}`}
          sub={`${data.land_size_hectare} hectare`}
        />
        <Tile
          icon="🌱"
          label="Stage"
          value={STAGE_LABELS[data.crop_stage_hint] ?? data.crop_stage_hint}
          sub={
            data.days_since_sowing >= 0
              ? `${data.days_since_sowing} days after sowing`
              : `sowing in ${Math.abs(data.days_since_sowing)} days`
          }
        />
        <Tile
          icon="🧪"
          label="Soil data"
          value={soilLabel}
          sub={soil?.soil_type ?? undefined}
        />
      </div>

      {weather && (
        <p className="mt-3 text-base text-soil-700">
          🌦️ {weather.temp_min_c}–{weather.temp_max_c}°C · {weather.humidity_pct}% humidity ·{" "}
          {weather.rainfall_last_7d_mm} mm rain in the last 7 days ·{" "}
          {weather.rainfall_forecast_7d_mm} mm expected next 7 days
        </p>
      )}

      {data.warnings.length > 0 && (
        <ul className="mt-4 space-y-2">
          {data.warnings.map((warning, index) => (
            <li
              key={index}
              className="flex gap-2 rounded-xl bg-amber-50 px-3 py-2 text-base text-amber-900"
            >
              <span aria-hidden>⚠️</span>
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
