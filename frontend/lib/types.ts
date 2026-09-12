/**
 * The TypeScript half of the shared contract.
 *
 * MUST stay in sync with backend/models/schemas.py. If you change a Pydantic
 * model there, change it here in the same commit - nothing enforces this
 * automatically yet.
 *
 * TODO(tooling): generate this file from the FastAPI OpenAPI schema
 * (`npx openapi-typescript http://127.0.0.1:8001/openapi.json`) once the
 * shape stops moving, and delete the hand-written duplication.
 */

// ---------------------------------------------------------------------------
// STEP 1 - farmer input
// ---------------------------------------------------------------------------

export type LandUnit = "acre" | "hectare" | "bigha" | "guntha";

export type IrrigationSource =
  | "rainfed"
  | "canal"
  | "borewell"
  | "tubewell"
  | "tank_pond"
  | "drip_sprinkler"
  | "other";

export type CropIntent = "current" | "planned";

export type Season = "kharif" | "rabi" | "zaid" | "perennial";

/** Exactly the body every POST /api/* endpoint accepts. */
export interface FarmInput {
  farmer_name?: string | null;
  pincode: string;
  village?: string | null;
  latitude?: number | null;
  longitude?: number | null;

  land_size: number;
  land_unit: LandUnit;

  crop_name: string;
  crop_intent: CropIntent;
  sowing_date: string; // ISO date, "YYYY-MM-DD"

  irrigation_source: IrrigationSource;
  soil_test_available: boolean;
  soil_health_card_id?: string | null;

  // --- manual soil test values (Part B) - only meaningful when
  // soil_test_available=true; any left null fall back to the Soil Health
  // Card lookup / district average server-side.
  soil_test_n_kg_per_ha?: number | null;
  soil_test_p_kg_per_ha?: number | null;
  soil_test_k_kg_per_ha?: number | null;
  soil_test_ph?: number | null;
  soil_test_organic_carbon_pct?: number | null;

  // --- crop photo health check (Part B) - set from the result of
  // POST /api/crop-health-check, not a raw file. Null if no photo taken.
  crop_health_score?: number | null;
}

// ---------------------------------------------------------------------------
// STEP 2 - auto-fetched reference data
// ---------------------------------------------------------------------------

export type SoilMatchLevel = "exact_pincode" | "district" | "state" | "none";

export interface LocationInfo {
  pincode: string;
  village?: string | null;
  block?: string | null;
  district?: string | null;
  state?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  resolved: boolean;
  source: string;
}

export interface SoilData {
  sample_id?: string | null;
  state?: string | null;
  district?: string | null;
  block?: string | null;
  village?: string | null;
  pincode?: string | null;
  soil_type?: string | null;
  test_date?: string | null;

  n_kg_per_ha?: number | null;
  p_kg_per_ha?: number | null;
  k_kg_per_ha?: number | null;
  ph?: number | null;
  ec_ds_per_m?: number | null;
  organic_carbon_pct?: number | null;

  s_ppm?: number | null;
  zn_ppm?: number | null;
  fe_ppm?: number | null;
  cu_ppm?: number | null;
  mn_ppm?: number | null;
  b_ppm?: number | null;

  match_level: SoilMatchLevel;
  records_averaged: number;
  source: string;
}

export interface WeatherDay {
  date: string;
  rain_mm: number;
  temp_max_c: number;
  temp_min_c: number;
  condition: string;
}

export interface WeatherData {
  source: string;
  as_of: string;
  latitude?: number | null;
  longitude?: number | null;
  temp_max_c: number;
  temp_min_c: number;
  humidity_pct: number;
  rainfall_last_7d_mm: number;
  rainfall_last_30d_mm: number;
  rainfall_forecast_7d_mm: number;
  et0_mm_per_day: number;
  forecast: WeatherDay[];
}

export interface CropReference {
  crop_name: string;
  aliases: string[];
  local_names: Record<string, string>;
  season: Season;
  n_requirement_kg_per_ha: number;
  p_requirement_kg_per_ha: number;
  k_requirement_kg_per_ha: number;
  water_requirement_mm: number;
  typical_irrigation_count?: number | null;
  ideal_soil_ph: { min: number; max: number };
  rotation_compatible_with: string[];
  rotation_avoid: string[];
  cover_crops: string[];
  growth_duration_days: number;
  growth_duration_days_range?: number[] | null;
  critical_irrigation_stages: {
    stage: string;
    days_after_sowing: number;
    note?: string | null;
  }[];
  is_legume: boolean;
  notes?: string | null;
  source?: string | null;
}

// ---------------------------------------------------------------------------
// STEP 3 - the merged object (arrives as ModuleResponse.details from /api/aggregate)
// ---------------------------------------------------------------------------

export interface AggregatedData {
  request_id: string;
  generated_at: string;
  farm_input: FarmInput;
  land_size_hectare: number;
  days_since_sowing: number;
  crop_stage_hint: string;
  location: LocationInfo;
  soil?: SoilData | null;
  weather?: WeatherData | null;
  crop_reference?: CropReference | null;
  data_gaps: string[];
  warnings: string[];
  completeness: number;
}

// ---------------------------------------------------------------------------
// STEP 4 - THE shared output envelope
// ---------------------------------------------------------------------------

export type ModuleStatus = "ok" | "partial" | "error";

/**
 * Every module endpoint returns exactly this. The dashboard renders any
 * ModuleResponse with the same card, so adding a 5th module on the backend
 * needs zero frontend work.
 */
export interface ModuleResponse<TDetails = Record<string, unknown>> {
  module_name: string;
  status: ModuleStatus;
  summary: string;
  details: TDetails;
  confidence: number | null;
  timestamp: string;
}

export interface AnalyzeResponse {
  aggregate: ModuleResponse<AggregatedData>;
  modules: ModuleResponse[];
}

export interface CropOption {
  crop_name: string;
  local_name?: string | null;
  season: string;
}

// ---------------------------------------------------------------------------
// Module-specific `details` shapes
//
// These describe what the CURRENT dummy modules put in `details`. When a real
// model replaces a module it should keep these keys and may add more.
// ---------------------------------------------------------------------------

export interface NutrientReading {
  key: string;
  label: string;
  value: number;
  unit: string;
  rating: "low" | "medium" | "high" | null;
  rating_hi: string | null;
  low_below: number;
  high_above: number;
}

export interface SoilStatusDetails {
  sample: {
    sample_id?: string | null;
    match_level: SoilMatchLevel;
    records_averaged: number;
    village?: string | null;
    block?: string | null;
    district?: string | null;
    state?: string | null;
    soil_type?: string | null;
    test_date?: string | null;
    source: string;
  } | null;
  nutrients: NutrientReading[];
  ph: { value: number | null; code: string; text: string; fits_crop: boolean | null } | null;
  ec: { value: number | null; code: string; text: string } | null;
  deficiencies: string[];
  fertiliser_plan: {
    basis: string;
    per_hectare: { N_kg: number; P2O5_kg: number; K2O_kg: number };
    for_your_field: {
      area_hectare: number;
      urea_kg: number;
      dap_kg: number;
      mop_kg: number;
      urea_bags_45kg: number;
      dap_bags_50kg: number;
      mop_bags_50kg: number;
    };
    note: string;
  } | null;
  farmer_actions: string[];
  is_dummy_data?: boolean;
}

export interface IrrigationDetails {
  action:
    | "irrigate_now"
    | "irrigate_soon"
    | "wait"
    | "none"
    | "conserve"
    | "pre_sowing"
    | "stop"
    | "unknown";
  irrigate_in_days: number | null;
  depth_mm: number | null;
  water_litres: number | null;
  irrigation_source?: string;
  irrigation_source_label?: string;
  source_capacity_mm_per_season?: number | null;
  application_efficiency?: number;
  crop_stage?: string;
  crop_coefficient_kc?: number;
  water_balance: {
    demand_next_7d_mm: number;
    et0_mm_per_day: number;
    rain_last_7d_mm: number;
    rain_forecast_7d_mm: number;
    effective_rain_mm: number;
    deficit_mm: number;
  } | null;
  seasonal_note?: string | null;
  next_critical_stage: {
    stage: string;
    days_after_sowing: number;
    days_from_today: number;
    note?: string | null;
  } | null;
  forecast?: WeatherDay[];
  weather_source?: string;
  farmer_actions: string[];
  is_dummy_data?: boolean;
}

export interface CropSuggestion {
  crop_name: string;
  local_name: string | null;
  score: number;
  season: string;
  season_label: string;
  water_requirement_mm: number;
  duration_days: number;
  is_legume: boolean;
  reasons: string[];
  warnings: string[];
}

export interface CropRecommendationDetails {
  target_season: string | null;
  season_window?: string;
  after_crop?: string;
  available_water_mm?: number;
  recommendations: CropSuggestion[];
  considered_count: number;
  scoring_method?: string;
  farmer_actions: string[];
  is_dummy_data?: boolean;
}

export interface RotationStep {
  sequence: number;
  season: string;
  season_label: string;
  window: string;
  crop_name: string;
  local_name: string | null;
  is_legume: boolean;
  duration_days: number;
  water_requirement_mm: number;
  reason: string;
}

export interface RotationDetails {
  current_crop: string;
  current_crop_local_name?: string | null;
  first_window?: string;
  plan: RotationStep[];
  avoid: string[];
  compatible_with?: string[];
  planning_method?: string;
  farmer_actions: string[];
  is_dummy_data?: boolean;
}

/** Shape of the 422 body produced by main.py's validation handler. */
export interface ApiValidationError {
  status: "error";
  message: string;
  errors: { field: string; message: string }[];
  timestamp: string;
}

// ---------------------------------------------------------------------------
// PART B - Regenerative Intelligence Engine
// ---------------------------------------------------------------------------

export interface RotationSuggestion {
  crop_name: string;
  local_name: string | null;
  is_legume: boolean;
  score: number;
  season: string;
  season_label: string;
  n_requirement_kg_per_ha: number;
  water_requirement_mm: number;
  reasons: string[];
}

export interface RegenRotationDetails {
  current_crop?: string;
  season_window?: string;
  severity_used?: string;
  next_crop_suggestions: RotationSuggestion[];
  reason: string;
  avoid?: string[];
  is_dummy_data?: boolean;
}

export interface SoilHealthProjectionPoint {
  season: number;
  soil_health_score: number;
}

export interface RegenSoilHealthDetails {
  soil_health_score: number;
  trend: string;
  flag: string;
  severity: "low" | "moderate" | "severe";
  projection: {
    current_practice: SoilHealthProjectionPoint[];
    regenerative_practice: SoilHealthProjectionPoint[];
  };
  assumptions?: string;
  is_dummy_data?: boolean;
}

export interface FertilizerExplanationEntry {
  feature: string;
  contribution_pct: number;
}

export interface RegenFertilizerDetails {
  current_crop?: string;
  growth_stage?: string;
  recommended_npk: {
    N_kg_per_ha: number;
    P_kg_per_ha: number;
    K_kg_per_ha: number;
    N_kg_for_field: number;
    P_kg_for_field: number;
    K_kg_for_field: number;
  } | null;
  current_estimated_usage: { N_kg_per_ha: number; P_kg_per_ha: number; K_kg_per_ha: number } | null;
  reduction_percent: number | null;
  explanation: FertilizerExplanationEntry[];
  farmer_actions?: string[];
  is_dummy_data?: boolean;
}

export interface CoverCropSuggestion {
  rank: number;
  cover_crop: string;
  nitrogen_fixing_speed: "fast" | "medium" | "none" | "unknown";
  water_need: string;
  knn_similar_farm_preference: number;
}

export interface RegenCoverCroppingDetails {
  current_crop?: string;
  cover_crop_suggestions: CoverCropSuggestion[];
  benefit: string;
  is_dummy_data?: boolean;
}

export interface RegenIrrigationDetails {
  irrigation_source?: string;
  irrigation_source_label?: string;
  next_irrigation_date: string | null;
  water_volume_mm: number | null;
  water_volume_litres?: number;
  note: string;
  water_balance?: {
    demand_next_7d_mm: number;
    et0_mm_per_day?: number;
    rain_last_7d_mm: number;
    rain_forecast_7d_mm: number;
    deficit_mm: number;
  } | null;
  cumulative_water_saved_liters: number;
  is_dummy_data?: boolean;
}

export type RegenConfidenceLabel = "High" | "Estimated";

export type RegenModuleConfidence = "observed" | "district_avg" | "estimated";

export interface RegenBreakdownEntry {
  score: number;
  weight: number;
  confidence: RegenModuleConfidence;
}

export interface RegenScoreDriver {
  factor: string;
  impact: string;
}

export interface RegenHistoryPoint {
  date: string;
  score: number;
}

export interface RegenHistory {
  farm_id: string;
  history: RegenHistoryPoint[];
  trend: string;
}

/**
 * Part C's Output Contract (backend/regeneration_score/). score/confidence/
 * breakdown are null together only when all 5 modules failed - see
 * score_engine.py's edge-case handling. `history`/`score_drivers` stay null
 * until Steps 7/8 are built - never faked as empty-looking real output.
 */
export interface RegenerationScore {
  score: number | null;
  confidence: RegenConfidenceLabel | null;
  breakdown: (Record<string, RegenBreakdownEntry> & { _conflicts?: string[] }) | null;
  score_tone?: string | null;
  weakest_module?: string | null;
  improvement_tip?: string | null;
  message?: string | null;
  history?: RegenHistory | null;
  score_drivers?: RegenScoreDriver[] | null;
}

export interface RegenAnalyzeResponse {
  module_1_rotation: ModuleResponse<RegenRotationDetails>;
  module_2_soil_health: ModuleResponse<RegenSoilHealthDetails>;
  module_3_fertilizer: ModuleResponse<RegenFertilizerDetails>;
  module_4_cover_cropping: ModuleResponse<RegenCoverCroppingDetails>;
  module_5_irrigation: ModuleResponse<RegenIrrigationDetails>;
  regeneration_score: RegenerationScore;
}

export interface CropHealthCheckResponse {
  health_score: number;
  label: string;
  is_placeholder: boolean;
  note: string;
}
