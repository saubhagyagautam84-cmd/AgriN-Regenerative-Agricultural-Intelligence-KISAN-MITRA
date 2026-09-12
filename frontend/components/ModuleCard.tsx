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

const MODULE_META: Record<string, { icon: string; title: string; hint: string }> = {
  soil_status: { icon: "🧪", title: "Soil health", hint: "मिट्टी की सेहत" },
  irrigation_advice: { icon: "💧", title: "Water & irrigation", hint: "सिंचाई" },
  crop_recommendation: { icon: "🌾", title: "What to grow next", hint: "अगली फसल" },
  rotation_suggestion: { icon: "🔄", title: "Crop rotation plan", hint: "फसल चक्र" },
  aggregator: { icon: "📋", title: "Farm details", hint: "खेत की जानकारी" },
  // --- Part B: Regenerative Intelligence Engine ---
  rotation: { icon: "🔄", title: "Rotation advisor", hint: "फसल चक्र सलाह" },
  soil_health: { icon: "🌱", title: "Soil carbon & health", hint: "मिट्टी कार्बन" },
  fertilizer: { icon: "🧪", title: "Fertiliser reducer", hint: "खाद घटाएँ" },
  cover_cropping: { icon: "🍃", title: "Cover cropping", hint: "कवर फसल" },
  irrigation_efficiency: { icon: "💧", title: "Water-use efficiency", hint: "जल दक्षता" },
};

const STATUS_META: Record<ModuleStatus, { label: string; className: string; icon: string }> = {
  ok: { label: "Ready", className: "bg-crop-100 text-crop-700", icon: "✅" },
  partial: {
    label: "Some data missing",
    className: "bg-amber-100 text-amber-900",
    icon: "⚠️",
  },
  error: { label: "Not available", className: "bg-red-100 text-red-900", icon: "❌" },
};

function titleise(moduleName: string): string {
  return moduleName.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ModuleCard({ response }: { response: ModuleResponse<any> }) {
  const meta = MODULE_META[response.module_name] ?? {
    icon: "📦",
    title: titleise(response.module_name),
    hint: "",
  };
  const status = STATUS_META[response.status] ?? STATUS_META.error;
  const isDummy = (response.details as { is_dummy_data?: boolean })?.is_dummy_data;

  return (
    <section
      data-testid={`module-card-${response.module_name}`}
      className="flex flex-col rounded-2xl border-2 border-soil-100 bg-white p-5 shadow-sm"
    >
      {/* ---- envelope: title + status ---- */}
      <header className="flex items-start justify-between gap-3">
        <h3 className="flex items-center gap-3 text-2xl font-bold leading-tight">
          <span aria-hidden className="text-3xl">
            {meta.icon}
          </span>
          <span>
            {meta.title}
            {meta.hint && (
              <span className="block text-sm font-normal text-soil-700">{meta.hint}</span>
            )}
          </span>
        </h3>
        <span
          className={`shrink-0 rounded-full px-3 py-1 text-sm font-bold ${status.className}`}
          title={`status: ${response.status}`}
        >
          <span aria-hidden>{status.icon}</span> {status.label}
        </span>
      </header>

      {/* ---- envelope: summary (the one line a farmer must read) ---- */}
      <p className="mt-4 text-xl font-semibold leading-snug">{response.summary}</p>

      {/* ---- envelope: confidence (ML modules only) ---- */}
      {response.confidence != null && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-sm font-semibold text-soil-700">
            <span>How sure are we?</span>
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
              "Please try again in a moment."}
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
              DEMO DATA
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
