"use client";

/**
 * STEP 1 - the farmer input form.
 *
 * Only 8 things are asked for, 3 of them optional. Everything else (soil
 * card, weather, crop agronomy, district) is fetched server-side from the
 * PIN code and crop name - see docs/field-spec.md for the full field table.
 *
 * Design constraints, because the user may have low digital literacy:
 *   - one visual row per idea, never two questions side by side
 *   - choices are big tap targets, not dropdowns, wherever there are <= 7 options
 *   - every label carries a Hindi subtitle
 *   - errors appear under the field in plain language, never as a code
 */

import { useEffect, useMemo, useState } from "react";
import { checkCropHealth, fetchCropOptions } from "@/lib/api";
import type {
  CropIntent,
  CropOption,
  FarmInput,
  IrrigationSource,
  LandUnit,
} from "@/lib/types";

// --------------------------------------------------------------------------
// Choice tables (labels live in the UI, values match the Pydantic enums)
// --------------------------------------------------------------------------

const LAND_UNITS: { value: LandUnit; label: string; hint: string }[] = [
  { value: "acre", label: "Acre", hint: "एकड़" },
  { value: "hectare", label: "Hectare", hint: "हेक्टेयर" },
  { value: "bigha", label: "Bigha", hint: "बीघा" },
  { value: "guntha", label: "Guntha", hint: "गुंठा" },
];

const IRRIGATION_SOURCES: {
  value: IrrigationSource;
  label: string;
  hint: string;
  icon: string;
}[] = [
  { value: "rainfed", label: "Rain only", hint: "बारिश", icon: "🌧️" },
  { value: "canal", label: "Canal", hint: "नहर", icon: "🌊" },
  { value: "borewell", label: "Borewell", hint: "बोरवेल", icon: "🕳️" },
  { value: "tubewell", label: "Tubewell", hint: "ट्यूबवेल", icon: "⛲" },
  { value: "tank_pond", label: "Tank / pond", hint: "तालाब", icon: "🏞️" },
  { value: "drip_sprinkler", label: "Drip / sprinkler", hint: "ड्रिप", icon: "💧" },
];

const CROP_INTENTS: { value: CropIntent; label: string; hint: string; icon: string }[] = [
  { value: "current", label: "Already sown", hint: "बो दिया है", icon: "🌱" },
  { value: "planned", label: "Planning to sow", hint: "बोने वाला हूँ", icon: "📅" },
];

// Shown if the backend is unreachable, so the form is never unusable.
const FALLBACK_CROPS: CropOption[] = [
  { crop_name: "Wheat", local_name: "गेहूँ", season: "rabi" },
  { crop_name: "Rice", local_name: "धान", season: "kharif" },
  { crop_name: "Maize", local_name: "मक्का", season: "kharif" },
  { crop_name: "Cotton", local_name: "कपास", season: "kharif" },
  { crop_name: "Soybean", local_name: "सोयाबीन", season: "kharif" },
];

const OTHER_CROP = "__other__";

// --------------------------------------------------------------------------

interface FormState {
  farmer_name: string;
  pincode: string;
  village: string;
  land_size: string;
  land_unit: LandUnit;
  crop_choice: string; // a crop name, or OTHER_CROP
  crop_other: string;
  crop_intent: CropIntent;
  sowing_date: string;
  irrigation_source: IrrigationSource;
  soil_test_available: boolean;
  soil_health_card_id: string;
  latitude: number | null;
  longitude: number | null;
  // --- Part B additions ---
  soil_test_n: string;
  soil_test_p: string;
  soil_test_k: string;
  soil_test_ph: string;
  soil_test_organic_carbon: string;
  crop_health_score: number | null;
}

type PhotoStatus = "idle" | "uploading" | "done" | "failed";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function initialState(): FormState {
  return {
    farmer_name: "",
    pincode: "",
    village: "",
    land_size: "",
    land_unit: "acre",
    crop_choice: "",
    crop_other: "",
    crop_intent: "current",
    // Filled in on mount, not here: computing a date during SSR and again on
    // the client can produce two different values and a hydration mismatch.
    sowing_date: "",
    irrigation_source: "rainfed",
    soil_test_available: false,
    soil_health_card_id: "",
    latitude: null,
    longitude: null,
    soil_test_n: "",
    soil_test_p: "",
    soil_test_k: "",
    soil_test_ph: "",
    soil_test_organic_carbon: "",
    crop_health_score: null,
  };
}

/** Blank string -> null, otherwise the parsed number (or null if not finite). */
function numOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Client-side validation. Mirrors the Pydantic validators in
 * backend/models/schemas.py - the server re-checks everything, this just
 * saves the farmer a round trip.
 */
function validate(state: FormState): Record<string, string> {
  const errors: Record<string, string> = {};

  if (!/^[1-9][0-9]{5}$/.test(state.pincode.trim())) {
    errors.pincode = "Enter the 6-digit PIN code of your village.";
  }

  const size = Number(state.land_size);
  if (!state.land_size.trim() || Number.isNaN(size)) {
    errors.land_size = "Enter how much land you farm.";
  } else if (size <= 0) {
    errors.land_size = "Land size must be more than zero.";
  } else if (size > 10000) {
    errors.land_size = "That seems too large. Please check the number.";
  }

  const cropName =
    state.crop_choice === OTHER_CROP ? state.crop_other.trim() : state.crop_choice.trim();
  if (!cropName) {
    errors.crop_name = "Choose the crop you are growing.";
  } else if (cropName.length < 2) {
    errors.crop_name = "Crop name is too short.";
  }

  if (!state.sowing_date) {
    errors.sowing_date = "Choose the sowing date.";
  } else {
    const sowing = new Date(state.sowing_date);
    const now = new Date();
    const oneYear = 365 * 24 * 60 * 60 * 1000;
    if (Number.isNaN(sowing.getTime())) {
      errors.sowing_date = "That date is not valid.";
    } else if (sowing.getTime() < now.getTime() - oneYear) {
      errors.sowing_date = "Date is more than a year old. Please check it.";
    } else if (sowing.getTime() > now.getTime() + oneYear) {
      errors.sowing_date = "Date is more than a year ahead. Please check it.";
    }
  }

  return errors;
}

interface Props {
  onSubmit: (input: FarmInput) => void;
  loading: boolean;
  /** Field errors returned by the backend's 422 handler. */
  serverFieldErrors?: Record<string, string>;
}

export default function FarmInputForm({ onSubmit, loading, serverFieldErrors }: Props) {
  const [state, setState] = useState<FormState>(initialState);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState(false);
  const [crops, setCrops] = useState<CropOption[]>(FALLBACK_CROPS);
  const [geoStatus, setGeoStatus] = useState<"idle" | "loading" | "done" | "failed">("idle");
  const [photoStatus, setPhotoStatus] = useState<PhotoStatus>("idle");
  const [photoNote, setPhotoNote] = useState<string>("");

  // Default the sowing date to today, on the client only (see initialState).
  useEffect(() => {
    setState((previous) =>
      previous.sowing_date ? previous : { ...previous, sowing_date: todayIso() },
    );
  }, []);

  // Crop list comes from the backend so crop_reference.json stays the single
  // source of truth - add a crop there and it appears here on next load.
  useEffect(() => {
    let cancelled = false;
    fetchCropOptions().then((options) => {
      if (!cancelled && options.length > 0) setCrops(options);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const shownErrors = useMemo(
    () => ({ ...errors, ...(serverFieldErrors ?? {}) }),
    [errors, serverFieldErrors],
  );

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setState((previous) => {
      const next = { ...previous, [key]: value };
      if (touched) setErrors(validate(next));
      return next;
    });
  }

  // NOTE: not named `useX` on purpose - it is a click handler, not a hook.
  function requestLocation() {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoStatus("failed");
      return;
    }
    setGeoStatus("loading");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setState((previous) => ({
          ...previous,
          latitude: Number(position.coords.latitude.toFixed(5)),
          longitude: Number(position.coords.longitude.toFixed(5)),
        }));
        setGeoStatus("done");
      },
      () => setGeoStatus("failed"),
      { timeout: 8000 },
    );
  }

  // STEP 4 - crop photo health check (Part B). Never blocks the form: a
  // failed or skipped upload just leaves crop_health_score null, and the
  // backend assumes a baseline health of 1.0 for it.
  async function handlePhotoSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setPhotoStatus("uploading");
    const result = await checkCropHealth(file);
    setState((previous) => ({ ...previous, crop_health_score: result.health_score }));
    setPhotoNote(result.note);
    setPhotoStatus(result.is_placeholder ? "done" : "done");
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);

    const found = validate(state);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      // Move the farmer to the first thing that needs fixing.
      document.querySelector<HTMLElement>("[data-field-error='true']")?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      return;
    }

    const cropName =
      state.crop_choice === OTHER_CROP ? state.crop_other.trim() : state.crop_choice.trim();

    onSubmit({
      farmer_name: state.farmer_name.trim() || null,
      pincode: state.pincode.trim(),
      village: state.village.trim() || null,
      latitude: state.latitude,
      longitude: state.longitude,
      land_size: Number(state.land_size),
      land_unit: state.land_unit,
      crop_name: cropName,
      crop_intent: state.crop_intent,
      sowing_date: state.sowing_date,
      irrigation_source: state.irrigation_source,
      soil_test_available: state.soil_test_available,
      soil_health_card_id: state.soil_test_available
        ? state.soil_health_card_id.trim() || null
        : null,
      soil_test_n_kg_per_ha: state.soil_test_available ? numOrNull(state.soil_test_n) : null,
      soil_test_p_kg_per_ha: state.soil_test_available ? numOrNull(state.soil_test_p) : null,
      soil_test_k_kg_per_ha: state.soil_test_available ? numOrNull(state.soil_test_k) : null,
      soil_test_ph: state.soil_test_available ? numOrNull(state.soil_test_ph) : null,
      soil_test_organic_carbon_pct: state.soil_test_available
        ? numOrNull(state.soil_test_organic_carbon)
        : null,
      crop_health_score: state.crop_health_score,
    });
  }

  const errorFor = (field: string) => shownErrors[field];

  return (
    <form onSubmit={handleSubmit} className="space-y-7" noValidate>
      {/* ---------------- 1. Location ---------------- */}
      <Field
        label="PIN code of your village"
        hint="अपने गाँव का पिन कोड"
        required
        error={errorFor("pincode")}
      >
        <input
          data-testid="input-pincode"
          className={`text-input ${errorFor("pincode") ? "text-input-error" : ""}`}
          inputMode="numeric"
          autoComplete="postal-code"
          maxLength={6}
          placeholder="e.g. 141001"
          value={state.pincode}
          onChange={(event) => set("pincode", event.target.value.replace(/\D/g, ""))}
        />
        <button
          type="button"
          onClick={requestLocation}
          className="mt-2 text-base font-semibold text-crop-700 underline underline-offset-4"
        >
          {geoStatus === "loading" && "Finding your location…"}
          {geoStatus === "done" && `📍 Location added (${state.latitude}, ${state.longitude})`}
          {geoStatus === "failed" && "Could not get location — PIN code is enough"}
          {geoStatus === "idle" && "📍 Or use my current location (optional)"}
        </button>
      </Field>

      {/* ---------------- 2. Land size ---------------- */}
      <Field
        label="How much land?"
        hint="कितनी ज़मीन है?"
        required
        error={errorFor("land_size")}
      >
        <input
          data-testid="input-land-size"
          className={`text-input ${errorFor("land_size") ? "text-input-error" : ""}`}
          inputMode="decimal"
          placeholder="e.g. 2.5"
          value={state.land_size}
          onChange={(event) => set("land_size", event.target.value.replace(/[^\d.]/g, ""))}
        />
        <div className="mt-3 grid grid-cols-4 gap-2">
          {LAND_UNITS.map((unit) => (
            <button
              key={unit.value}
              type="button"
              onClick={() => set("land_unit", unit.value)}
              className={`choice-chip flex-col !gap-0 ${
                state.land_unit === unit.value ? "choice-chip-active" : ""
              }`}
            >
              <span>{unit.label}</span>
              <span className="text-xs font-normal opacity-70">{unit.hint}</span>
            </button>
          ))}
        </div>
      </Field>

      {/* ---------------- 3. Crop ---------------- */}
      <Field
        label="Which crop?"
        hint="कौन सी फसल?"
        required
        error={errorFor("crop_name")}
      >
        <select
          data-testid="select-crop"
          className={`text-input ${errorFor("crop_name") ? "text-input-error" : ""}`}
          value={state.crop_choice}
          onChange={(event) => set("crop_choice", event.target.value)}
        >
          <option value="">— Select a crop —</option>
          {crops.map((crop) => (
            <option key={crop.crop_name} value={crop.crop_name}>
              {crop.crop_name}
              {crop.local_name ? ` / ${crop.local_name}` : ""}
            </option>
          ))}
          <option value={OTHER_CROP}>Other crop (type it myself)</option>
        </select>

        {state.crop_choice === OTHER_CROP && (
          <input
            className="text-input mt-3"
            placeholder="Type the crop name"
            value={state.crop_other}
            onChange={(event) => set("crop_other", event.target.value)}
          />
        )}

        <div className="mt-3 grid grid-cols-2 gap-2">
          {CROP_INTENTS.map((intent) => (
            <button
              key={intent.value}
              type="button"
              onClick={() => set("crop_intent", intent.value)}
              className={`choice-chip ${
                state.crop_intent === intent.value ? "choice-chip-active" : ""
              }`}
            >
              <span aria-hidden>{intent.icon}</span>
              <span className="flex flex-col items-start leading-tight">
                <span>{intent.label}</span>
                <span className="text-xs font-normal opacity-70">{intent.hint}</span>
              </span>
            </button>
          ))}
        </div>
      </Field>

      {/* ---------------- 4. Sowing date ---------------- */}
      <Field
        label={state.crop_intent === "planned" ? "Planned sowing date" : "Sowing date"}
        hint="बुवाई की तारीख"
        required
        error={errorFor("sowing_date")}
      >
        <input
          type="date"
          className={`text-input ${errorFor("sowing_date") ? "text-input-error" : ""}`}
          value={state.sowing_date}
          onChange={(event) => set("sowing_date", event.target.value)}
        />
      </Field>

      {/* ---------------- 5. Irrigation ---------------- */}
      <Field label="Where does your water come from?" hint="पानी कहाँ से आता है?" required>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {IRRIGATION_SOURCES.map((source) => (
            <button
              key={source.value}
              type="button"
              data-testid={`irrigation-${source.value}`}
              onClick={() => set("irrigation_source", source.value)}
              className={`choice-chip flex-col !gap-1 py-3 ${
                state.irrigation_source === source.value ? "choice-chip-active" : ""
              }`}
            >
              <span className="text-2xl" aria-hidden>
                {source.icon}
              </span>
              <span className="text-sm leading-tight">{source.label}</span>
              <span className="text-xs font-normal opacity-70">{source.hint}</span>
            </button>
          ))}
        </div>
      </Field>

      {/* ---------------- 6. Soil test ---------------- */}
      <Field label="Do you have a soil test report?" hint="क्या मिट्टी जाँच रिपोर्ट है?">
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            data-testid="soil-test-yes"
            onClick={() => set("soil_test_available", true)}
            className={`choice-chip ${state.soil_test_available ? "choice-chip-active" : ""}`}
          >
            ✅ Yes / हाँ
          </button>
          <button
            type="button"
            data-testid="soil-test-no"
            onClick={() => set("soil_test_available", false)}
            className={`choice-chip ${!state.soil_test_available ? "choice-chip-active" : ""}`}
          >
            ❌ No / नहीं
          </button>
        </div>
        {state.soil_test_available && (
          <>
            <input
              className="text-input mt-3"
              placeholder="Soil Health Card number (optional)"
              value={state.soil_health_card_id}
              onChange={(event) => set("soil_health_card_id", event.target.value)}
            />

            {/* Part B: manual N/P/K/pH/organic carbon. All optional - any
                left blank fall back to the Soil Health Card / district
                average server-side (see feature_resolver.py). */}
            <div className="mt-3 rounded-xl bg-soil-50 p-3">
              <p className="text-sm font-semibold text-soil-700">
                If you know your soil test numbers, enter them (optional) / मिट्टी जाँच के आंकड़े (वैकल्पिक)
              </p>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                <NumberField testId="input-soil-n" label="N (kg/ha)" value={state.soil_test_n} onChange={(v) => set("soil_test_n", v)} />
                <NumberField testId="input-soil-p" label="P (kg/ha)" value={state.soil_test_p} onChange={(v) => set("soil_test_p", v)} />
                <NumberField testId="input-soil-k" label="K (kg/ha)" value={state.soil_test_k} onChange={(v) => set("soil_test_k", v)} />
                <NumberField testId="input-soil-ph" label="pH" value={state.soil_test_ph} onChange={(v) => set("soil_test_ph", v)} />
                <NumberField
                  testId="input-soil-oc"
                  label="Organic carbon (%)"
                  value={state.soil_test_organic_carbon}
                  onChange={(v) => set("soil_test_organic_carbon", v)}
                />
              </div>
            </div>
          </>
        )}
      </Field>

      {/* ---------------- 6b. Crop photo (Part B, optional) ---------------- */}
      <Field
        label="Photo of your crop (optional)"
        hint="फसल की फोटो — ज़रूरी नहीं, इससे सलाह बेहतर होगी"
      >
        <input
          type="file"
          data-testid="input-crop-photo"
          accept="image/*"
          capture="environment"
          className="text-input"
          onChange={handlePhotoSelected}
        />
        {photoStatus === "uploading" && (
          <p data-testid="photo-status-uploading" className="mt-2 text-base text-soil-700">Checking your photo…</p>
        )}
        {photoStatus === "done" && (
          <p data-testid="photo-status-done" className="mt-2 text-base text-crop-700">✅ {photoNote}</p>
        )}
      </Field>

      {/* ---------------- 7. Optional details ---------------- */}
      <details className="rounded-xl border-2 border-soil-100 bg-white px-4 py-3">
        <summary className="cursor-pointer text-lg font-semibold">
          Your name and village (optional)
          <span className="field-hint">नाम और गाँव — ज़रूरी नहीं</span>
        </summary>
        <div className="mt-4 space-y-4">
          <input
            className="text-input"
            placeholder="Your name"
            value={state.farmer_name}
            onChange={(event) => set("farmer_name", event.target.value)}
          />
          <input
            className="text-input"
            placeholder="Village name"
            value={state.village}
            onChange={(event) => set("village", event.target.value)}
          />
        </div>
      </details>

      <button
        type="submit"
        data-testid="submit-farm-form"
        disabled={loading}
        className="touch-target w-full rounded-2xl bg-crop-600 py-4 text-xl font-bold text-white
                   shadow-lg transition hover:bg-crop-700 disabled:cursor-not-allowed disabled:bg-soil-100
                   disabled:text-soil-700"
      >
        {loading ? "Checking your farm…" : "Get my farm advice / सलाह देखें"}
      </button>
    </form>
  );
}

// --------------------------------------------------------------------------

function NumberField({
  label,
  value,
  onChange,
  testId,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  testId?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-soil-700">{label}</span>
      <input
        data-testid={testId}
        className="text-input mt-1 !py-2 !text-base"
        inputMode="decimal"
        placeholder="—"
        value={value}
        onChange={(event) => onChange(event.target.value.replace(/[^\d.]/g, ""))}
      />
    </label>
  );
}

function Field({
  label,
  hint,
  required,
  error,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div data-field-error={error ? "true" : "false"}>
      <label className="field-label">
        {label}
        {required && <span className="ml-1 text-red-600">*</span>}
        {hint && <span className="field-hint">{hint}</span>}
      </label>
      <div className="mt-2">{children}</div>
      {error && (
        <p className="mt-2 flex items-start gap-2 text-base font-semibold text-red-700">
          <span aria-hidden>⚠️</span>
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
