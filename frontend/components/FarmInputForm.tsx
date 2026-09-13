"use client";

/**
 * The 4-step farm input wizard, ported from kisan-sathi-frontend.html (the
 * approved design/interaction prototype) - structure, copy and step
 * boundaries follow that file; this version backs it with real React state
 * instead of DOM manipulation, and wires every field to the real
 * validation/API logic that already existed here.
 *
 * Steps (matches the prototype exactly):
 *   1. Farm location & land   - PIN code, geolocation, land size + unit
 *   2. Crop & sowing          - crop, sowing status, sowing date
 *   3. Water & soil           - irrigation source, soil test + N/P/K/pH/OC
 *   4. Photo & optional info  - crop photo, name/village
 * Only steps 1 and 2 block advancing (matches the prototype); 3 and 4 are
 * fully optional. Submitting step 4 calls the real onSubmit - there is no
 * fake setTimeout anywhere in this file.
 *
 * Once the parent has a real result (`hasResult`), this component renders
 * nothing: the wizard's progress bar/step-nav genuinely disappear rather
 * than just having their content swapped (a prototype bug this project
 * deliberately avoids reintroducing - see STEP 6 of the integration brief).
 *
 * Design constraints, because the user may have low digital literacy:
 *   - one visual row per idea, never two questions side by side
 *   - choices are big tap targets, not dropdowns, wherever there are <= 7 options
 *   - every label is translated via the i18n system (see lib/i18n/)
 *   - errors appear under the field in plain language, never as a code
 */

import { useEffect, useMemo, useState } from "react";
import { checkCropHealth, fetchCropOptions } from "@/lib/api";
import { useI18n } from "@/lib/i18n/I18nContext";
import { speak } from "@/lib/voice/speech";
import type {
  CropIntent,
  CropOption,
  FarmInput,
  IrrigationSource,
  LandUnit,
} from "@/lib/types";

const LAND_UNIT_VALUES: LandUnit[] = ["acre", "hectare", "bigha", "guntha"];
const IRRIGATION_SOURCE_VALUES: { value: IrrigationSource; icon: string }[] = [
  { value: "rainfed", icon: "🌧️" },
  { value: "canal", icon: "🌊" },
  { value: "borewell", icon: "🕳️" },
  { value: "tubewell", icon: "⛲" },
  { value: "tank_pond", icon: "🏞️" },
  { value: "drip_sprinkler", icon: "💧" },
];
const CROP_INTENT_VALUES: { value: CropIntent; icon: string }[] = [
  { value: "current", icon: "🌱" },
  { value: "planned", icon: "📅" },
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
type WizardStep = 1 | 2 | 3 | 4;

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
 * saves the farmer a round trip. Takes `t` so messages are translated.
 */
function validate(state: FormState, t: (key: string) => string): Record<string, string> {
  const errors: Record<string, string> = {};

  if (!/^[1-9][0-9]{5}$/.test(state.pincode.trim())) {
    errors.pincode = t("form.validation.pincode");
  }

  const size = Number(state.land_size);
  if (!state.land_size.trim() || Number.isNaN(size)) {
    errors.land_size = t("form.validation.landSizeRequired");
  } else if (size <= 0) {
    errors.land_size = t("form.validation.landSizeTooSmall");
  } else if (size > 10000) {
    errors.land_size = t("form.validation.landSizeTooLarge");
  }

  const cropName =
    state.crop_choice === OTHER_CROP ? state.crop_other.trim() : state.crop_choice.trim();
  if (!cropName) {
    errors.crop_name = t("form.validation.cropRequired");
  } else if (cropName.length < 2) {
    errors.crop_name = t("form.validation.cropTooShort");
  }

  if (!state.sowing_date) {
    errors.sowing_date = t("form.validation.sowingDateRequired");
  } else {
    const sowing = new Date(state.sowing_date);
    const now = new Date();
    const oneYear = 365 * 24 * 60 * 60 * 1000;
    if (Number.isNaN(sowing.getTime())) {
      errors.sowing_date = t("form.validation.sowingDateInvalid");
    } else if (sowing.getTime() < now.getTime() - oneYear) {
      errors.sowing_date = t("form.validation.sowingDateTooOld");
    } else if (sowing.getTime() > now.getTime() + oneYear) {
      errors.sowing_date = t("form.validation.sowingDateTooFuture");
    }
  }

  return errors;
}

/** Only steps 1 and 2 block advancing - matches the prototype exactly. */
function stepBlockingFields(step: WizardStep): string[] {
  if (step === 1) return ["pincode", "land_size"];
  if (step === 2) return ["crop_name", "sowing_date"];
  return [];
}

interface Props {
  onSubmit: (input: FarmInput) => void;
  loading: boolean;
  /** Field errors returned by the backend's 422 handler. */
  serverFieldErrors?: Record<string, string>;
  /** The last submit attempt's error message, if any (network/API failure). */
  submitError?: string | null;
  /** True once the parent has a real result - the wizard fully hides itself. */
  hasResult: boolean;
}

export default function FarmInputForm({
  onSubmit,
  loading,
  serverFieldErrors,
  submitError,
  hasResult,
}: Props) {
  const { t, language } = useI18n();
  const [step, setStep] = useState<WizardStep>(1);
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

  if (hasResult) return null;

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setState((previous) => {
      const next = { ...previous, [key]: value };
      if (touched) setErrors(validate(next, t));
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

  // Crop photo health check (Part B). Never blocks the wizard: a failed,
  // skipped, or unsupported-crop upload just leaves crop_health_score null,
  // and the backend assumes a baseline health of 1.0 for it.
  async function handlePhotoSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    const cropName =
      state.crop_choice === OTHER_CROP ? state.crop_other.trim() : state.crop_choice.trim();
    if (!cropName) {
      setPhotoNote(t("form.photo.chooseCropFirst"));
      setPhotoStatus("done");
      return;
    }

    setPhotoStatus("uploading");
    const result = await checkCropHealth(file, cropName);
    setState((previous) => ({ ...previous, crop_health_score: result.health_score }));
    setPhotoNote(result.note);
    setPhotoStatus("done");
  }

  function submitFarm() {
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

  function goNext() {
    setTouched(true);
    const found = validate(state, t);
    setErrors(found);

    const blocked = stepBlockingFields(step).some((field) => found[field]);
    if (blocked) {
      document.querySelector<HTMLElement>("[data-field-error='true']")?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      return;
    }

    if (step === 4) {
      submitFarm();
      return;
    }
    setStep((previous) => (Math.min(previous + 1, 4) as WizardStep));
    document.getElementById("wizard-top")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function goBack() {
    setStep((previous) => (Math.max(previous - 1, 1) as WizardStep));
    document.getElementById("wizard-top")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const errorFor = (field: string) => shownErrors[field];

  const locationButtonText =
    geoStatus === "loading"
      ? t("form.locationButton.loading")
      : geoStatus === "done"
        ? `${t("form.locationButton.done")} (${state.latitude}, ${state.longitude})`
        : geoStatus === "failed"
          ? t("form.locationButton.failed")
          : t("form.locationButton.idle");

  const stepTitle = t(`wizard.step${step}.title`);
  const stepSubtitle = t(`wizard.step${step}.subtitle`);

  return (
    // Bottom padding reserves room for .step-nav's fixed-bottom bar on
    // mobile (matches the prototype's `.app{padding:0 16px 100px}`) - removed
    // once the nav goes static at 860px, so the last field of any step is
    // never left sitting underneath the bar.
    <div id="wizard-top" className="pb-24 min-[860px]:pb-0">
      {/* ---------------- progress ---------------- */}
      <div className="mb-4" data-testid="wizard-progress">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-bold" style={{ color: "var(--green-900)" }}>
            {t("wizard.stepOf", { n: step })}
          </span>
        </div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${(Math.min(step, 4) / 4) * 100}%` }} />
        </div>
        <div className="mt-2.5 flex gap-1.5">
          {[1, 2, 3, 4].map((dot) => (
            <div key={dot} className={`step-dot ${dot < step ? "done" : ""}`} />
          ))}
        </div>
      </div>

      {/* ---------------- step card ---------------- */}
      <div className="wizard-card" data-testid="wizard-step" data-step={step} key={step}>
        <div className="mb-4 flex items-start justify-between gap-2.5">
          <div>
            <p className="m-0 mb-1 text-lg font-extrabold text-soil-900">{stepTitle}</p>
            <p className="m-0 text-sm text-soil-700">{stepSubtitle}</p>
          </div>
          <button
            type="button"
            className="voice-btn"
            aria-label={t("wizard.voiceReadAria")}
            onClick={() => speak(`${stepTitle}. ${stepSubtitle}`, language)}
          >
            🔊
          </button>
        </div>

        {step === 1 && (
          <>
            <Field label={t("form.pincode.label")} required error={errorFor("pincode")}>
              <input
                data-testid="input-pincode"
                className={`text-input ${errorFor("pincode") ? "text-input-error" : ""}`}
                inputMode="numeric"
                autoComplete="off"
                maxLength={6}
                placeholder={t("form.pincode.placeholder")}
                value={state.pincode}
                onChange={(event) => set("pincode", event.target.value.replace(/\D/g, ""))}
              />
              <button
                type="button"
                onClick={requestLocation}
                className="mt-2 text-base font-semibold text-crop-700 underline underline-offset-4"
              >
                {locationButtonText}
              </button>
            </Field>

            <Field label={t("form.landSize.label")} required error={errorFor("land_size")}>
              <input
                data-testid="input-land-size"
                className={`text-input ${errorFor("land_size") ? "text-input-error" : ""}`}
                inputMode="decimal"
                autoComplete="off"
                placeholder={t("form.landSize.placeholder")}
                value={state.land_size}
                onChange={(event) => set("land_size", event.target.value.replace(/[^\d.]/g, ""))}
              />
              <div className="mt-3 grid grid-cols-4 gap-2">
                {LAND_UNIT_VALUES.map((unit) => (
                  <button
                    key={unit}
                    type="button"
                    onClick={() => set("land_unit", unit)}
                    className={`card-btn !min-h-[2.75rem] flex-row ${
                      state.land_unit === unit ? "selected" : ""
                    }`}
                  >
                    <span className="label">{t(`form.landUnit.${unit}`)}</span>
                  </button>
                ))}
              </div>
            </Field>
          </>
        )}

        {step === 2 && (
          <>
            <Field label={t("form.crop.label")} required error={errorFor("crop_name")}>
              <select
                data-testid="select-crop"
                className={`text-input ${errorFor("crop_name") ? "text-input-error" : ""}`}
                value={state.crop_choice}
                onChange={(event) => set("crop_choice", event.target.value)}
              >
                <option value="">{t("form.crop.selectPlaceholder")}</option>
                {crops.map((crop) => (
                  <option key={crop.crop_name} value={crop.crop_name}>
                    {crop.crop_name}
                    {crop.local_name ? ` / ${crop.local_name}` : ""}
                  </option>
                ))}
                <option value={OTHER_CROP}>{t("form.crop.otherOption")}</option>
              </select>

              {state.crop_choice === OTHER_CROP && (
                <input
                  className="text-input mt-3"
                  autoComplete="off"
                  placeholder={t("form.crop.otherPlaceholder")}
                  value={state.crop_other}
                  onChange={(event) => set("crop_other", event.target.value)}
                />
              )}
            </Field>

            <Field label={t("form.cropIntent.label")}>
              <div className="grid grid-cols-2 gap-2">
                {CROP_INTENT_VALUES.map((intent) => (
                  <button
                    key={intent.value}
                    type="button"
                    onClick={() => set("crop_intent", intent.value)}
                    className={`card-btn ${state.crop_intent === intent.value ? "selected" : ""}`}
                  >
                    <span className="ico" aria-hidden>
                      {intent.icon}
                    </span>
                    <span className="label">{t(`form.cropIntent.${intent.value}`)}</span>
                  </button>
                ))}
              </div>
            </Field>

            <Field
              label={
                state.crop_intent === "planned"
                  ? t("form.sowingDate.labelPlanned")
                  : t("form.sowingDate.label")
              }
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
          </>
        )}

        {step === 3 && (
          <>
            <Field label={t("form.irrigationSource.label")} required>
              {/* Matches the prototype exactly: 3 columns by default, only
                  dropping to 2 under 360px - not the other way around. */}
              <div className="grid grid-cols-3 gap-2 max-[359px]:grid-cols-2">
                {IRRIGATION_SOURCE_VALUES.map((source) => (
                  <button
                    key={source.value}
                    type="button"
                    data-testid={`irrigation-${source.value}`}
                    onClick={() => set("irrigation_source", source.value)}
                    className={`card-btn ${
                      state.irrigation_source === source.value ? "selected" : ""
                    }`}
                  >
                    <span className="ico" aria-hidden>
                      {source.icon}
                    </span>
                    <span className="label">{t(`form.irrigationSource.${source.value}`)}</span>
                  </button>
                ))}
              </div>
            </Field>

            <Field label={t("form.soilTest.label")}>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  data-testid="soil-test-yes"
                  onClick={() => set("soil_test_available", true)}
                  className={`card-btn flex-row !gap-2 ${state.soil_test_available ? "selected" : ""}`}
                >
                  <span className="label">{t("form.soilTest.yes")}</span>
                </button>
                <button
                  type="button"
                  data-testid="soil-test-no"
                  onClick={() => set("soil_test_available", false)}
                  className={`card-btn flex-row !gap-2 ${!state.soil_test_available ? "selected" : ""}`}
                >
                  <span className="label">{t("form.soilTest.no")}</span>
                </button>
              </div>
              {state.soil_test_available && (
                <div id="soilFields">
                  <input
                    className="text-input mt-3"
                    autoComplete="off"
                    placeholder={t("form.soilTest.cardIdPlaceholder")}
                    value={state.soil_health_card_id}
                    onChange={(event) => set("soil_health_card_id", event.target.value)}
                  />

                  {/* Part B: manual N/P/K/pH/organic carbon. All optional -
                      any left blank fall back to the Soil Health Card /
                      district average server-side (see feature_resolver.py). */}
                  <div className="mt-3 rounded-xl bg-soil-50 p-3">
                    <p className="text-sm font-semibold text-soil-700">{t("form.soilTest.numbersIntro")}</p>
                    {/* Prototype keeps this grid at a fixed 2 columns regardless of width. */}
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <NumberField testId="input-soil-n" label={t("form.soilTest.n")} value={state.soil_test_n} onChange={(v) => set("soil_test_n", v)} />
                      <NumberField testId="input-soil-p" label={t("form.soilTest.p")} value={state.soil_test_p} onChange={(v) => set("soil_test_p", v)} />
                      <NumberField testId="input-soil-k" label={t("form.soilTest.k")} value={state.soil_test_k} onChange={(v) => set("soil_test_k", v)} />
                      <NumberField testId="input-soil-ph" label={t("form.soilTest.ph")} value={state.soil_test_ph} onChange={(v) => set("soil_test_ph", v)} />
                      <NumberField
                        testId="input-soil-oc"
                        label={t("form.soilTest.organicCarbon")}
                        value={state.soil_test_organic_carbon}
                        onChange={(v) => set("soil_test_organic_carbon", v)}
                      />
                    </div>
                  </div>
                </div>
              )}
            </Field>
          </>
        )}

        {step === 4 && (
          <>
            <Field label={t("form.photo.label")}>
              <p className="helper-note">{t("form.photo.supportedCropsNote")}</p>
              <label className="file-drop mt-2 block" htmlFor="crop-photo-input">
                <span className="ico block" aria-hidden>📷</span>
                <span className="block font-bold text-crop-700">{t("form.photo.tapToChoose")}</span>
              </label>
              <input
                type="file"
                id="crop-photo-input"
                data-testid="input-crop-photo"
                accept="image/*"
                capture="environment"
                className="sr-only"
                onChange={handlePhotoSelected}
              />
              {photoStatus === "uploading" && (
                <p data-testid="photo-status-uploading" className="mt-2 text-base text-soil-700">{t("form.photo.uploading")}</p>
              )}
              {photoStatus === "done" && (
                <p data-testid="photo-status-done" className="mt-2 text-base text-crop-700">✅ {photoNote}</p>
              )}
            </Field>

            <details className="collapse">
              <summary>
                <span>{t("form.optionalDetails.summary")}</span>
                <span aria-hidden>▾</span>
              </summary>
              <div className="inner space-y-3">
                <input
                  className="text-input"
                  autoComplete="off"
                  placeholder={t("form.optionalDetails.namePlaceholder")}
                  value={state.farmer_name}
                  onChange={(event) => set("farmer_name", event.target.value)}
                />
                <input
                  className="text-input"
                  autoComplete="off"
                  placeholder={t("form.optionalDetails.villagePlaceholder")}
                  value={state.village}
                  onChange={(event) => set("village", event.target.value)}
                />
              </div>
            </details>

            {submitError && (
              <p className="error-text mt-3" role="alert">
                {submitError}
              </p>
            )}
          </>
        )}
      </div>

      {/* ---------------- nav ---------------- */}
      <nav className="step-nav mt-5">
        <div className="mx-auto flex max-w-[640px] gap-2.5 lg:max-w-none">
          {step > 1 && (
            <button type="button" data-testid="wizard-back" onClick={goBack} className="btn-secondary">
              {t("wizard.back")}
            </button>
          )}
          <button
            type="button"
            data-testid={step === 4 ? "submit-farm-form" : "wizard-next"}
            onClick={goNext}
            disabled={loading}
            className="btn-primary"
          >
            {step === 4 ? (loading ? t("form.submit.loading") : t("form.submit.idle")) : t("wizard.next")}
          </button>
        </div>
      </nav>
    </div>
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
        autoComplete="off"
        placeholder="—"
        value={value}
        onChange={(event) => onChange(event.target.value.replace(/[^\d.]/g, ""))}
      />
    </label>
  );
}

function Field({
  label,
  required,
  error,
  children,
}: {
  label?: string;
  required?: boolean;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="field-group mb-5" data-field-error={error ? "true" : "false"}>
      {label && (
        <label className="field-label">
          {label}
          {required && <span className="ml-1 text-danger">*</span>}
        </label>
      )}
      <div className="mt-2">{children}</div>
      {error && (
        <p className="error-text flex items-start gap-2">
          <span aria-hidden>⚠️</span>
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
