"use client";

/**
 * STEP 5 - the dashboard.
 *
 * Flow:
 *   farmer fills the form (STEP 1)
 *     -> POST /api/aggregate          (STEP 3, backbone object)
 *     -> POST the 4 module endpoints  (STEP 4, one envelope each)
 *     -> render one card per module, all from the same ModuleResponse shape
 *
 * Everything below the summary strip is DEMO DATA produced by rule-based
 * stubs in backend/services/modules/. Each card shows a "DEMO DATA" badge
 * until its module sets `details.is_dummy_data = false`.
 *
 * TODO(ML): nothing on this page needs to change when a real model lands.
 * That is the point - the contract is `ModuleResponse`, not the model.
 */

import { useRef, useState } from "react";
import FarmInputForm from "@/components/FarmInputForm";
import FarmSummary from "@/components/FarmSummary";
import ModuleCard from "@/components/ModuleCard";
import RegenScoreCard from "@/components/RegenScoreCard";
import { API_BASE, ApiError, runAnalysis, runRegenAnalysis, type AnalysisResult } from "@/lib/api";
import type { FarmInput, RegenAnalyzeResponse } from "@/lib/types";

/** One-tap demo so the team can show the dashboard without typing. */
const DEMO_FARM: FarmInput = {
  farmer_name: "Ramesh Kumar",
  pincode: "141001",
  village: "Pakhowal",
  latitude: null,
  longitude: null,
  land_size: 2.5,
  land_unit: "acre",
  crop_name: "Wheat",
  crop_intent: "current",
  sowing_date: new Date(Date.now() - 40 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
  irrigation_source: "borewell",
  soil_test_available: true,
  soil_health_card_id: null,
};

export default function DashboardPage() {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [regenResult, setRegenResult] = useState<RegenAnalyzeResponse | null>(null);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const resultsRef = useRef<HTMLDivElement>(null);

  async function analyse(input: FarmInput) {
    setLoading(true);
    setError(null);
    setFieldErrors({});
    setRegenError(null);

    try {
      const analysis = await runAnalysis(input);
      setResult(analysis);
      // Give React a tick to paint the cards before scrolling to them.
      window.setTimeout(
        () => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
        50,
      );
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFieldErrors(caught.fieldErrors);
      } else {
        setError("Something went wrong. Please try again.");
      }
      setResult(null);
      setLoading(false);
      return;
    }
    setLoading(false);

    // Part B runs independently - a failure here never blocks Part A's
    // dashboard, which has already rendered above.
    try {
      setRegenResult(await runRegenAnalysis(input));
    } catch (caught) {
      setRegenError(caught instanceof ApiError ? caught.message : "Regenerative advice could not be loaded.");
      setRegenResult(null);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      {/* ------------------------------ header ------------------------------ */}
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold leading-tight sm:text-4xl">
            <span aria-hidden className="mr-2">
              🌾
            </span>
            Kisan Sathi
          </h1>
          <p className="mt-1 text-lg text-soil-700">
            Tell us 4 things about your farm. We will do the rest.
            <span className="block text-base">
              अपने खेत की 4 बातें बताइए — बाकी हम देख लेंगे।
            </span>
          </p>
        </div>

        <button
          type="button"
          onClick={() => analyse(DEMO_FARM)}
          disabled={loading}
          className="touch-target rounded-xl border-2 border-crop-600 px-4 text-base font-bold
                     text-crop-700 transition hover:bg-crop-50 disabled:opacity-50"
        >
          ▶ Load demo farm
        </button>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:items-start">
        {/* ------------------------------ form ------------------------------ */}
        <div className="rounded-2xl border-2 border-soil-100 bg-white p-5 shadow-sm lg:sticky lg:top-6">
          <h2 className="mb-5 text-xl font-bold">
            Your farm details
            <span className="block text-sm font-normal text-soil-700">खेत की जानकारी</span>
          </h2>
          <FarmInputForm
            onSubmit={analyse}
            loading={loading}
            serverFieldErrors={fieldErrors}
          />
        </div>

        {/* ---------------------------- results ---------------------------- */}
        <div ref={resultsRef} className="space-y-6">
          {error && (
            <div className="rounded-2xl border-2 border-red-300 bg-red-50 p-5">
              <h2 className="flex items-center gap-2 text-xl font-bold text-red-900">
                <span aria-hidden>❌</span> Could not get your advice
              </h2>
              <p className="mt-2 text-lg text-red-900">{error}</p>
              <p className="mt-3 text-sm text-red-800">
                Backend expected at <code className="font-mono">{API_BASE}</code>. Start it with{" "}
                <code className="font-mono">uvicorn main:app --reload --port 8001</code> from the{" "}
                <code className="font-mono">backend/</code> folder.
              </p>
            </div>
          )}

          {loading && <LoadingSkeleton />}

          {!loading && !result && !error && <EmptyState />}

          {!loading && result && (
            <>
              <FarmSummary response={result.aggregate} />

              <div className="grid gap-5 xl:grid-cols-2">
                {result.modules.map((module) => (
                  <ModuleCard key={module.module_name} response={module} />
                ))}
              </div>

              <p className="rounded-xl bg-soil-100 px-4 py-3 text-sm text-soil-700">
                <strong>For the team:</strong> every card above is one{" "}
                <code className="font-mono">ModuleResponse</code> from its own endpoint. All
                advisory numbers are rule-based placeholders — swap a module in{" "}
                <code className="font-mono">backend/services/modules/</code> and this page picks
                it up with no frontend change.
              </p>

              {/* ---------------- Part B: Regenerative Intelligence Engine ---------------- */}
              <div data-testid="regen-section" className="mt-8 border-t-2 border-dashed border-soil-100 pt-8">
                <h2 className="text-2xl font-extrabold">
                  <span aria-hidden className="mr-2">🌿</span>
                  Regenerative Intelligence Engine
                  <span className="block text-base font-normal text-soil-700">
                    पुनर्जनन बुद्धिमत्ता इंजन — Part B
                  </span>
                </h2>

                {regenError && (
                  <div className="mt-4 rounded-2xl border-2 border-red-300 bg-red-50 p-4 text-red-900">
                    {regenError}
                  </div>
                )}

                {!regenError && !regenResult && (
                  <div className="mt-4 h-32 animate-pulse rounded-2xl bg-crop-100" />
                )}

                {regenResult && (
                  <div className="mt-4 space-y-5">
                    <RegenScoreCard regen={regenResult.regeneration_score} />
                    <div className="grid gap-5 xl:grid-cols-2">
                      <ModuleCard response={regenResult.module_1_rotation} />
                      <ModuleCard response={regenResult.module_2_soil_health} />
                      <ModuleCard response={regenResult.module_3_fertilizer} />
                      <ModuleCard response={regenResult.module_4_cover_cropping} />
                      <ModuleCard response={regenResult.module_5_irrigation} />
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <footer className="mt-10 border-t border-soil-100 pt-4 text-center text-sm text-soil-700">
        Part A skeleton · soil + weather + crop data are placeholders compiled from ICAR
        guidelines · not yet fit for real farm decisions
      </footer>
    </main>
  );
}

// --------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="space-y-5">
      <div className="h-32 animate-pulse rounded-2xl bg-crop-100" />
      <div className="grid gap-5 xl:grid-cols-2">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="h-64 animate-pulse rounded-2xl bg-soil-100" />
        ))}
      </div>
      <p className="text-center text-lg text-soil-700">
        Checking your soil, weather and crop… / जाँच हो रही है…
      </p>
    </div>
  );
}

function EmptyState() {
  const steps = [
    { icon: "🧪", label: "Soil health", hint: "मिट्टी की सेहत" },
    { icon: "💧", label: "Water & irrigation", hint: "सिंचाई" },
    { icon: "🌾", label: "What to grow next", hint: "अगली फसल" },
    { icon: "🔄", label: "Crop rotation plan", hint: "फसल चक्र" },
  ];

  return (
    <div className="rounded-2xl border-2 border-dashed border-soil-100 bg-white/60 p-8 text-center">
      <p className="text-5xl" aria-hidden>
        👈
      </p>
      <h2 className="mt-3 text-2xl font-bold">Fill the form to see your advice</h2>
      <p className="mt-1 text-lg text-soil-700">You will get these four things:</p>
      <div className="mt-6 grid grid-cols-2 gap-4">
        {steps.map((step) => (
          <div key={step.label} className="rounded-xl bg-soil-50 px-3 py-4">
            <div className="text-4xl" aria-hidden>
              {step.icon}
            </div>
            <div className="mt-2 text-lg font-bold leading-tight">{step.label}</div>
            <div className="text-sm text-soil-700">{step.hint}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
