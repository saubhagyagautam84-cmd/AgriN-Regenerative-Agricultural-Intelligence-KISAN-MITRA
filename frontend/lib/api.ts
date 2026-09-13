/**
 * The only file that talks to FastAPI.
 *
 * Components never call `fetch` directly - swap transport, add auth or point
 * at a deployed backend by editing this file alone.
 */

import type {
  AggregatedData,
  AnalyzeResponse,
  ApiValidationError,
  CropHealthCheckResponse,
  CropOption,
  FarmInput,
  ModuleResponse,
  RegenAnalyzeResponse,
} from "./types";
import { getStoredSessionToken } from "./auth/session";

/**
 * Port 8001, not 8000 - port 8000 was already occupied on the machine this
 * was built on. Override with NEXT_PUBLIC_API_BASE_URL in .env.local.
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";

/**
 * false -> dashboard calls /api/aggregate, then the 4 module endpoints in
 *          parallel. Proves each module is independently swappable, which is
 *          the point of the skeleton.
 * true  -> one call to /api/analyze. Cheaper (aggregation runs once).
 *          Flip this when the module endpoints get expensive.
 */
export const USE_COMBINED_ENDPOINT = false;

/** The 4 module endpoints, in the order the dashboard renders them. */
export const MODULE_ENDPOINTS = [
  "/api/soil-status",
  "/api/irrigation-advice",
  "/api/crop-recommendation",
  "/api/rotation-suggestion",
] as const;

export class ApiError extends Error {
  /** Field-level messages from the backend's 422 handler, if any. */
  readonly fieldErrors: Record<string, string>;
  readonly status: number;

  constructor(message: string, status: number, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

function isValidationError(body: unknown): body is ApiValidationError {
  return (
    typeof body === "object" &&
    body !== null &&
    Array.isArray((body as ApiValidationError).errors)
  );
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch {
    // Almost always "uvicorn isn't running" during the hackathon.
    throw new ApiError(
      `Could not reach the server at ${API_BASE}. Is the backend running? ` +
        `(cd backend, then: uvicorn main:app --reload --port 8001)`,
      0,
    );
  }

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      /* non-JSON error body - fall through to the generic message */
    }

    if (response.status === 422 && isValidationError(body)) {
      const fieldErrors: Record<string, string> = {};
      for (const item of body.errors) {
        fieldErrors[item.field] = item.message;
      }
      throw new ApiError(body.message, 422, fieldErrors);
    }

    throw new ApiError(
      `Server error (${response.status}) from ${path}.`,
      response.status,
    );
  }

  return (await response.json()) as T;
}

/** Crop list for the form dropdown. Falls back to [] so the form still works. */
export async function fetchCropOptions(): Promise<CropOption[]> {
  try {
    const response = await fetch(`${API_BASE}/api/crops`, { cache: "no-store" });
    if (!response.ok) return [];
    return (await response.json()) as CropOption[];
  } catch {
    return [];
  }
}

export interface AnalysisResult {
  aggregate: ModuleResponse<AggregatedData>;
  modules: ModuleResponse[];
}

/**
 * The full dashboard flow: aggregate the farm, then run every module.
 *
 * A module that fails does NOT fail the whole dashboard - the backend already
 * converts a module crash into a `status: "error"` ModuleResponse, and the
 * catch below covers a network-level failure of one request.
 */
export async function runAnalysis(input: FarmInput): Promise<AnalysisResult> {
  if (USE_COMBINED_ENDPOINT) {
    const combined = await postJson<AnalyzeResponse>("/api/analyze", input);
    return { aggregate: combined.aggregate, modules: combined.modules };
  }

  // 1. aggregate first - if the input is invalid we find out here, once,
  //    and can show field errors without firing four more requests.
  const aggregate = await postJson<ModuleResponse<AggregatedData>>(
    "/api/aggregate",
    input,
  );

  // 2. then all four modules in parallel.
  const modules = await Promise.all(
    MODULE_ENDPOINTS.map(async (endpoint): Promise<ModuleResponse> => {
      try {
        return await postJson<ModuleResponse>(endpoint, input);
      } catch (error) {
        const message =
          error instanceof ApiError ? error.message : "Unexpected error.";
        return {
          module_name: endpoint.replace("/api/", "").replace(/-/g, "_"),
          status: "error",
          summary: "This advice could not be loaded. Please try again.",
          details: { error_message: message },
          confidence: null,
          timestamp: new Date().toISOString(),
        } satisfies ModuleResponse;
      }
    }),
  );

  return { aggregate, modules };
}

// ---------------------------------------------------------------------------
// PART B - Regenerative Intelligence Engine
// ---------------------------------------------------------------------------

/** Feature Resolver -> 5 modules -> Regeneration Score Engine, in one call. */
export async function runRegenAnalysis(input: FarmInput): Promise<RegenAnalyzeResponse> {
  return postJson<RegenAnalyzeResponse>("/api/regenerate", input);
}

/**
 * Uploads a crop photo for the CNN health check (STEP 4). Call this BEFORE
 * runRegenAnalysis if the farmer took a photo, and put the resulting
 * `health_score` into FarmInput.crop_health_score.
 *
 * `cropName` is required - the backend only recognises Corn/Maize, Potato
 * and Soybean (PlantVillage's coverage) and honestly reports
 * `label: "unsupported_crop"` for anything else rather than guessing.
 *
 * Never throws - a placeholder/baseline result comes back even if the
 * backend's model isn't trained yet (see backend/services/regen/cnn_health.py).
 */
export async function checkCropHealth(photo: File, cropName: string): Promise<CropHealthCheckResponse> {
  const formData = new FormData();
  formData.append("photo", photo);
  formData.append("crop_name", cropName);

  try {
    const response = await fetch(`${API_BASE}/api/crop-health-check`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    return (await response.json()) as CropHealthCheckResponse;
  } catch {
    return {
      health_score: 1.0,
      label: "unscored",
      is_placeholder: true,
      note: "Could not reach the health-check service - baseline health (1.0) assumed.",
    };
  }
}

// ---------------------------------------------------------------------------
// Family members (real login required) - see backend/services/auth.py
// ---------------------------------------------------------------------------

export interface FamilyMember {
  id: number;
  name: string;
  phone: string | null;
  created_at: string;
}

function authHeaders(): HeadersInit {
  const token = getStoredSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function listFamilyMembers(): Promise<FamilyMember[]> {
  const response = await fetch(`${API_BASE}/api/family-members`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (response.status === 401) throw new ApiError("not-logged-in", 401);
  if (!response.ok) throw new ApiError(`Server error (${response.status}).`, response.status);
  return (await response.json()) as FamilyMember[];
}

export async function addFamilyMember(name: string, phone: string | null): Promise<FamilyMember> {
  const response = await fetch(`${API_BASE}/api/family-members`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, phone }),
  });
  if (response.status === 401) throw new ApiError("not-logged-in", 401);
  if (!response.ok) throw new ApiError(`Server error (${response.status}).`, response.status);
  return (await response.json()) as FamilyMember;
}

export async function removeFamilyMember(id: number): Promise<void> {
  const response = await fetch(`${API_BASE}/api/family-members/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (response.status === 401) throw new ApiError("not-logged-in", 401);
  if (!response.ok) throw new ApiError(`Server error (${response.status}).`, response.status);
}
