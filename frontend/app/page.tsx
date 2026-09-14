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
import LanguageSwitcher from "@/components/LanguageSwitcher";
import MoreMenu from "@/components/MoreMenu";
import { useI18n } from "@/lib/i18n/I18nContext";
import { API_BASE, ApiError, runAnalysis, runRegenAnalysis, type AnalysisResult, type OfflineRegenAnalyzeResponse } from "@/lib/api";
import type { FarmInput } from "@/lib/types";

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
  const { t } = useI18n();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [regenResult, setRegenResult] = useState<OfflineRegenAnalyzeResponse | null>(null);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  // Bumped on "Home" to force FarmInputForm to remount fresh (resets its
  // internal wizard step back to 1, even mid-wizard) rather than just
  // clearing the result state, which only resets it when it was unmounted.
  const [resetKey, setResetKey] = useState(0);
  const [reportHint, setReportHint] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);

  function goHome() {
    setResult(null);
    setRegenResult(null);
    setRegenError(null);
    setError(null);
    setFieldErrors({});
    setLoading(false);
    setResetKey((key) => key + 1);
    setReportHint(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // "Check my report" (3-dot menu): jump to the last results if any exist
  // this visit, otherwise nudge the farmer to the wizard rather than
  // showing an empty/fake report page.
  function goToMyReport() {
    if (result) {
      setReportHint(false);
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    setReportHint(true);
    document.getElementById("wizard-top")?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => setReportHint(false), 5000);
  }

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
        setError(t("dashboard.genericError"));
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
      setRegenError(caught instanceof ApiError ? caught.message : t("dashboard.regenErrorFallback"));
      setRegenResult(null);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      {/* ------------------------------ header ------------------------------ */}
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <button
          type="button"
          data-testid="brand-home-link"
          onClick={goHome}
          className="text-left"
          aria-label={t("menu.home")}
        >
          <h1 className="text-3xl font-extrabold leading-tight sm:text-4xl">
            <span aria-hidden className="mr-2">
              🌾
            </span>
            {t("header.appName")}
          </h1>
          <p className="mt-1 text-lg text-soil-700">{t("header.tagline")}</p>
        </button>

        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <MoreMenu onHome={goHome} onMyReport={goToMyReport} />
          <button
            type="button"
            onClick={() => analyse(DEMO_FARM)}
            disabled={loading}
            className="touch-target rounded-xl border-2 border-crop-600 px-4 text-base font-bold
                       text-crop-700 transition hover:bg-crop-50 disabled:opacity-50"
          >
            {t("header.loadDemo")}
          </button>
        </div>
      </header>

      {/* 860px matches the prototype's own desktop breakpoint exactly (see
          globals.css .step-nav) rather than Tailwind's default lg: (1024px). */}
      <div className="grid gap-6 min-[860px]:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] min-[860px]:items-start">
        {/* ------------------------------ form ------------------------------ */}
        <div className="rounded-2xl border-2 border-soil-100 bg-surface p-5 shadow-sm min-[860px]:sticky min-[860px]:top-6">
          {result ? (
            <div className="text-center">
              <p className="text-lg font-bold text-crop-700">✅ {t("wizard.detailsSaved")}</p>
              <button
                type="button"
                className="btn-secondary mt-3 w-full"
                onClick={() => {
                  setResult(null);
                  setRegenResult(null);
                  setError(null);
                }}
              >
                {t("wizard.editDetails")}
              </button>
            </div>
          ) : (
            <>
              <h2 className="mb-5 text-xl font-bold">{t("form.sectionTitle")}</h2>
              {reportHint && (
                <p data-testid="report-hint" className="helper-note mb-4" role="status">
                  {t("menu.myReportNoneYet")}
                </p>
              )}
              <FarmInputForm
                key={resetKey}
                onSubmit={analyse}
                loading={loading}
                serverFieldErrors={fieldErrors}
                submitError={error}
                hasResult={false}
              />
            </>
          )}
        </div>

        {/* ---------------------------- results ---------------------------- */}
        <div ref={resultsRef} className="space-y-6">
          {error && (
            <div className="rounded-2xl border-2 border-red-300 bg-red-50 p-5">
              <h2 className="flex items-center gap-2 text-xl font-bold text-red-900">
                <span aria-hidden>❌</span> {t("dashboard.resultsErrorTitle")}
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
                {t("dashboard.teamNote")}
              </p>

              {/* ---------------- Part B: Regenerative Intelligence Engine ---------------- */}
              <div data-testid="regen-section" className="mt-8 border-t-2 border-dashed border-soil-100 pt-8">
                <h2 className="text-2xl font-extrabold">
                  <span aria-hidden className="mr-2">🌿</span>
                  {t("dashboard.regenSectionTitle")}
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
                    {regenResult._offlineCachedAt && (
                      <div
                        className="rounded-2xl border-2 border-amber-300 bg-amber-50 p-4 text-amber-900"
                        data-testid="offline-cached-report-banner"
                      >
                        {t("dashboard.offlineCachedReport")}
                      </div>
                    )}
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
        {t("dashboard.footer")}
      </footer>
    </main>
  );
}

// --------------------------------------------------------------------------

function LoadingSkeleton() {
  const { t } = useI18n();
  return (
    <div className="space-y-5">
      <div className="h-32 animate-pulse rounded-2xl bg-crop-100" />
      <div className="grid gap-5 xl:grid-cols-2">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="h-64 animate-pulse rounded-2xl bg-soil-100" />
        ))}
      </div>
      <p className="text-center text-lg text-soil-700">{t("dashboard.loadingText")}</p>
    </div>
  );
}

function EmptyState() {
  const { t } = useI18n();
  const steps = [
    { icon: "🧪", key: "soilHealth" },
    { icon: "💧", key: "waterIrrigation" },
    { icon: "🌾", key: "whatToGrow" },
    { icon: "🔄", key: "rotationPlan" },
  ] as const;

  return (
    <div className="rounded-2xl border-2 border-dashed border-soil-100 bg-surface/60 p-8 text-center">
      <p className="text-5xl" aria-hidden>
        👈
      </p>
      <h2 className="mt-3 text-2xl font-bold">{t("dashboard.emptyTitle")}</h2>
      <p className="mt-1 text-lg text-soil-700">{t("dashboard.emptySubtitle")}</p>
      <div className="mt-6 grid grid-cols-2 gap-4">
        {steps.map((step) => (
          <div key={step.key} className="rounded-xl bg-soil-50 px-3 py-4">
            <div className="text-4xl" aria-hidden>
              {step.icon}
            </div>
            <div className="mt-2 text-lg font-bold leading-tight">
              {t(`dashboard.emptySteps.${step.key}`)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
