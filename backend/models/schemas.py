"""
Shared data contracts for the whole backend.

Three groups live here:

1. FarmInput          -> what the farmer types into the Next.js form (STEP 1)
2. Soil/Weather/Crop  -> what the system auto-fetches (STEP 2)
   + AggregatedData   -> the single merged object every module reads (STEP 3)
3. ModuleResponse     -> the ONE output envelope every module writes (STEP 4)

Rule for anyone adding a module later (ML or otherwise):
    read from AggregatedData, return a ModuleResponse. Never invent a new
    response shape - the frontend only knows how to render ModuleResponse.

Keep this file in sync with frontend/lib/types.ts.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def now_iso() -> str:
    """UTC timestamp in ISO-8601 with a trailing Z. One format everywhere."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# Conversion factors to hectares. Note: a "bigha" is NOT standardised across
# India (it ranges from ~0.25 ha in UP/Bihar to ~0.4 ha in Rajasthan). We use
# the UP/Bihar pucca bigha and surface the assumption as a warning.
LAND_UNIT_TO_HECTARE: dict[str, float] = {
    "acre": 0.404686,
    "hectare": 1.0,
    "bigha": 0.2529,
    "guntha": 0.010117,
}


# --------------------------------------------------------------------------
# Enums (kept as plain str enums so they serialise straight to JSON)
# --------------------------------------------------------------------------


class LandUnit(str, Enum):
    ACRE = "acre"
    HECTARE = "hectare"
    BIGHA = "bigha"
    GUNTHA = "guntha"


class IrrigationSource(str, Enum):
    RAINFED = "rainfed"
    CANAL = "canal"
    BOREWELL = "borewell"
    TUBEWELL = "tubewell"
    TANK_POND = "tank_pond"
    DRIP_SPRINKLER = "drip_sprinkler"
    OTHER = "other"


class CropIntent(str, Enum):
    """Is the crop already in the ground, or is the farmer planning it?"""

    CURRENT = "current"
    PLANNED = "planned"


class Season(str, Enum):
    KHARIF = "kharif"
    RABI = "rabi"
    ZAID = "zaid"
    PERENNIAL = "perennial"


ModuleStatus = Literal["ok", "partial", "error"]


# --------------------------------------------------------------------------
# STEP 1 - the farmer-facing input contract
# --------------------------------------------------------------------------


class FarmInput(BaseModel):
    """
    Everything the farmer enters by hand. Deliberately small - target users
    have low digital literacy, so anything derivable is derived server-side.

    Mirrored in TypeScript as `FarmInput` in frontend/lib/types.ts.
    """

    model_config = ConfigDict(use_enum_values=True)

    # --- who / where -------------------------------------------------------
    farmer_name: Optional[str] = Field(
        default=None, max_length=80, description="Optional. Display only."
    )
    pincode: str = Field(
        ...,
        description="6-digit Indian PIN code. Primary location key for soil + weather.",
    )
    village: Optional[str] = Field(default=None, max_length=80)
    latitude: Optional[float] = Field(default=None, ge=6.0, le=38.0)
    longitude: Optional[float] = Field(default=None, ge=68.0, le=98.0)

    # --- the land ----------------------------------------------------------
    land_size: float = Field(..., gt=0, le=10_000, description="Area in `land_unit`.")
    land_unit: LandUnit = LandUnit.ACRE

    # --- the crop ----------------------------------------------------------
    crop_name: str = Field(..., min_length=2, max_length=60)
    crop_intent: CropIntent = CropIntent.CURRENT
    sowing_date: date = Field(
        ..., description="Actual sowing date, or planned date if crop_intent=planned."
    )

    # --- water + soil ------------------------------------------------------
    irrigation_source: IrrigationSource = IrrigationSource.RAINFED
    soil_test_available: bool = False
    soil_health_card_id: Optional[str] = Field(
        default=None,
        max_length=40,
        description="Soil Health Card / sample ID. Only meaningful if soil_test_available.",
    )

    # --- manual soil test values (Part B) -----------------------------------
    # Only meaningful when soil_test_available=True. Any left blank fall back
    # to the Soil Health Card lookup / district average via the Feature
    # Resolver (services/regen/feature_resolver.py) - never required.
    soil_test_n_kg_per_ha: Optional[float] = Field(default=None, ge=0, le=2000)
    soil_test_p_kg_per_ha: Optional[float] = Field(default=None, ge=0, le=500)
    soil_test_k_kg_per_ha: Optional[float] = Field(default=None, ge=0, le=2000)
    soil_test_ph: Optional[float] = Field(default=None, ge=2.0, le=11.0)
    soil_test_organic_carbon_pct: Optional[float] = Field(default=None, ge=0, le=10)

    # --- crop photo health check (Part B) -----------------------------------
    # The photo itself is uploaded separately via POST /api/crop-health-check
    # (multipart) - keeps this JSON contract file-free. The frontend calls
    # that endpoint first (if a photo was taken) and puts the resulting score
    # here before submitting the rest of the form.
    crop_health_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="0-1 health multiplier from the CNN health check. Null if no photo was taken.",
    )

    # --- validation --------------------------------------------------------

    @field_validator("pincode")
    @classmethod
    def _validate_pincode(cls, v: str) -> str:
        v = (v or "").strip()
        if not (len(v) == 6 and v.isdigit() and v[0] != "0"):
            raise ValueError("PIN code must be exactly 6 digits and cannot start with 0")
        return v

    @field_validator("crop_name")
    @classmethod
    def _clean_crop_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Crop name is required")
        return v

    @field_validator("farmer_name", "village", "soil_health_card_id")
    @classmethod
    def _blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip()
        return v or None

    @field_validator("sowing_date")
    @classmethod
    def _sane_sowing_date(cls, v: date) -> date:
        today = date.today()
        if v < today - timedelta(days=365):
            raise ValueError("Sowing date cannot be more than 1 year in the past")
        if v > today + timedelta(days=365):
            raise ValueError("Sowing date cannot be more than 1 year in the future")
        return v

    # --- derived -----------------------------------------------------------

    def land_size_hectare(self) -> float:
        unit = self.land_unit.value if isinstance(self.land_unit, LandUnit) else self.land_unit
        return round(self.land_size * LAND_UNIT_TO_HECTARE[unit], 4)


# --------------------------------------------------------------------------
# STEP 2 - auto-fetched reference data
# --------------------------------------------------------------------------

SoilMatchLevel = Literal["exact_pincode", "district", "state", "none"]


class LocationInfo(BaseModel):
    """Resolved administrative location. Built from pincode_lookup.csv."""

    pincode: str
    village: Optional[str] = None
    block: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    resolved: bool = False
    source: str = "pincode_lookup.csv"


class SoilData(BaseModel):
    """One Soil Health Card record (or a district-level average of several)."""

    sample_id: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    block: Optional[str] = None
    village: Optional[str] = None
    pincode: Optional[str] = None
    soil_type: Optional[str] = None
    test_date: Optional[str] = None

    # Macro nutrients, kg/ha (as reported on a Soil Health Card)
    n_kg_per_ha: Optional[float] = None
    p_kg_per_ha: Optional[float] = None
    k_kg_per_ha: Optional[float] = None

    ph: Optional[float] = None
    ec_ds_per_m: Optional[float] = None
    organic_carbon_pct: Optional[float] = None

    # Micro nutrients, ppm
    s_ppm: Optional[float] = None
    zn_ppm: Optional[float] = None
    fe_ppm: Optional[float] = None
    cu_ppm: Optional[float] = None
    mn_ppm: Optional[float] = None
    b_ppm: Optional[float] = None

    match_level: SoilMatchLevel = "none"
    records_averaged: int = 1
    source: str = "soil_health_card.csv"


class WeatherDay(BaseModel):
    date: str
    rain_mm: float
    temp_max_c: float
    temp_min_c: float
    condition: str


class WeatherData(BaseModel):
    """
    Weather + rainfall for the farm location.

    TODO(integration): replace the synthetic generator in services/weather.py
    with a real provider (Open-Meteo is free and key-less; IMD/AgroMet gives
    district advisories). This model is already shaped for that swap.
    """

    source: str = "synthetic-stub"
    as_of: str = Field(default_factory=now_iso)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    temp_max_c: float
    temp_min_c: float
    humidity_pct: float
    rainfall_last_7d_mm: float
    rainfall_last_30d_mm: float
    rainfall_forecast_7d_mm: float
    et0_mm_per_day: float = Field(
        ..., description="Reference evapotranspiration - drives the irrigation maths."
    )
    forecast: list[WeatherDay] = Field(default_factory=list)


class PhRange(BaseModel):
    min: float
    max: float


class IrrigationStage(BaseModel):
    stage: str
    days_after_sowing: int
    note: Optional[str] = None


class CropReference(BaseModel):
    """
    One entry from data/crop_reference.json, hand-compiled from ICAR
    package-of-practice guidelines.

    Field aliases map snake_case Python <-> the JSON keys agreed in STEP 2b.
    """

    model_config = ConfigDict(populate_by_name=True)

    crop_name: str
    aliases: list[str] = Field(default_factory=list)
    local_names: dict[str, str] = Field(default_factory=dict)
    season: Season = Season.KHARIF

    n_requirement_kg_per_ha: float = Field(..., alias="N_requirement")
    p_requirement_kg_per_ha: float = Field(..., alias="P_requirement")
    k_requirement_kg_per_ha: float = Field(..., alias="K_requirement")

    water_requirement_mm: float
    typical_irrigation_count: Optional[int] = None
    ideal_soil_ph: PhRange = Field(..., alias="ideal_soil_pH")

    rotation_compatible_with: list[str] = Field(default_factory=list)
    rotation_avoid: list[str] = Field(default_factory=list)
    cover_crops: list[str] = Field(default_factory=list)

    growth_duration_days: int
    growth_duration_days_range: Optional[list[int]] = None
    critical_irrigation_stages: list[IrrigationStage] = Field(default_factory=list)

    is_legume: bool = False
    notes: Optional[str] = None
    source: Optional[str] = None


# --------------------------------------------------------------------------
# STEP 3 - the merged object every module reads from
# --------------------------------------------------------------------------


class AggregatedData(BaseModel):
    """
    The backbone object. `aggregate_farm_data()` builds it; every module
    consumes it. Adding a new auto-fetched source means adding a field here,
    not changing any module signature.
    """

    request_id: str
    generated_at: str = Field(default_factory=now_iso)

    farm_input: FarmInput
    land_size_hectare: float
    days_since_sowing: int = Field(
        ..., description="Negative if the crop has not been sown yet."
    )
    crop_stage_hint: str = Field(
        default="unknown",
        description="Coarse phenology bucket derived from days_since_sowing.",
    )

    location: LocationInfo
    soil: Optional[SoilData] = None
    weather: Optional[WeatherData] = None
    crop_reference: Optional[CropReference] = None

    data_gaps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    completeness: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Fraction of the 4 sources resolved."
    )


# --------------------------------------------------------------------------
# STEP 4 - the one output envelope
# --------------------------------------------------------------------------


class ModuleResponse(BaseModel):
    """
    THE shared contract. Every module endpoint returns exactly this shape,
    so the dashboard can render any module with one card component and new
    modules need zero frontend work.

    `details` is intentionally free-form (module-specific), everything else
    is fixed.
    """

    module_name: str
    status: ModuleStatus = "ok"
    summary: str = Field(..., description="One line, farmer-readable, no jargon.")
    details: dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Null for rule-based modules. ML modules fill this in later.",
    )
    timestamp: str = Field(default_factory=now_iso)

    # --- convenience constructors so modules stay short --------------------

    @classmethod
    def ok(
        cls,
        module_name: str,
        summary: str,
        details: Optional[dict[str, Any]] = None,
        confidence: Optional[float] = None,
    ) -> "ModuleResponse":
        return cls(
            module_name=module_name,
            status="ok",
            summary=summary,
            details=details or {},
            confidence=confidence,
        )

    @classmethod
    def partial(
        cls,
        module_name: str,
        summary: str,
        details: Optional[dict[str, Any]] = None,
        confidence: Optional[float] = None,
    ) -> "ModuleResponse":
        return cls(
            module_name=module_name,
            status="partial",
            summary=summary,
            details=details or {},
            confidence=confidence,
        )

    @classmethod
    def error(
        cls,
        module_name: str,
        summary: str,
        details: Optional[dict[str, Any]] = None,
    ) -> "ModuleResponse":
        return cls(
            module_name=module_name,
            status="error",
            summary=summary,
            details=details or {},
            confidence=None,
        )


class AnalyzeResponse(BaseModel):
    """Convenience wrapper for `/api/analyze` - aggregate + all 4 modules."""

    aggregate: ModuleResponse
    modules: list[ModuleResponse]


class CropOption(BaseModel):
    """Lightweight crop entry for the form dropdown (`GET /api/crops`)."""

    crop_name: str
    local_name: Optional[str] = None
    season: str


# --------------------------------------------------------------------------
# PART B - Regenerative Intelligence Engine
# --------------------------------------------------------------------------

RegenConfidenceLabel = Literal["High", "Estimated", "Low confidence — mostly regional averages"]


class RegenerationScore(BaseModel):
    """
    Output of Part C's Regeneration Score Engine (backend/regeneration_score/) -
    the dashboard's headline number.

    `score`/`confidence`/`breakdown` are null together when all 5 modules
    failed - see regeneration_score/score_engine.py's edge-case handling.
    Never fabricate a 0 or 100 in that case; `message` explains why instead.
    """

    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    confidence: Optional[RegenConfidenceLabel] = None
    breakdown: Optional[dict[str, Any]] = None
    score_tone: Optional[str] = None
    weakest_module: Optional[str] = None
    improvement_tip: Optional[str] = None
    message: Optional[str] = Field(
        default=None, description="Set only when score/confidence/breakdown are null - explains why."
    )
    history: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Real, stored season-over-season scores once a second submission exists for this "
            "farm_id (see services/score_history.py); simulated from M2's 3-season projection "
            "for a farm_id's first-ever submission (regeneration_score/history_tracker.py). "
            "Carries a 'source': 'real'|'simulated' field so callers can tell which."
        ),
    )
    peer_comparison: Optional[dict[str, Any]] = Field(
        default=None,
        description="How this score compares to other real submissions nearby - see regeneration_score/peer_comparison.py. Null when too few nearby submissions exist yet to compare honestly.",
    )
    score_drivers: Optional[list[dict[str, Any]]] = Field(
        default=None, description="Ranked factors pulled from M1/M3's own explainability output - see regeneration_score/explainability.py."
    )


class RegenAnalyzeResponse(BaseModel):
    """
    Part B's full Output Contract. Each module_* field is a normal
    ModuleResponse (same envelope Part A's dashboard already renders) whose
    `details` holds that module's shape from the spec.
    """

    module_1_rotation: ModuleResponse
    module_2_soil_health: ModuleResponse
    module_3_fertilizer: ModuleResponse
    module_4_cover_cropping: ModuleResponse
    module_5_irrigation: ModuleResponse
    regeneration_score: RegenerationScore


class CropHealthCheckResponse(BaseModel):
    """Response of POST /api/crop-health-check (multipart photo upload)."""

    health_score: float = Field(..., ge=0.0, le=1.0)
    label: str
    is_placeholder: bool
    note: str


# --------------------------------------------------------------------------
# Auth + family members - see services/auth.py
# --------------------------------------------------------------------------


class AuthVerifyRequest(BaseModel):
    """Body of POST /api/auth/verify - a Firebase Phone Auth ID token."""

    id_token: str


class AuthVerifyResponse(BaseModel):
    session_token: str
    phone: str


class AuthMeResponse(BaseModel):
    phone: str


class FamilyMemberIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)


class FamilyMemberOut(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    created_at: int


# --------------------------------------------------------------------------
# Farmer-contributed soil data loop - see services/farmer_soil_observations.py
# --------------------------------------------------------------------------


class SoilObservationStats(BaseModel):
    """GET /api/soil-observations/stats - how many real farmer-submitted readings exist for a district, for transparency (and to feed the wizard's 'this helps others nearby' note)."""

    district: Optional[str] = None
    farmer_submitted_count: int
    official_soil_health_card_count: int


# --------------------------------------------------------------------------
# SMS/IVR fallback channel - see services/telephony.py
# --------------------------------------------------------------------------


class SmsInboundRequest(BaseModel):
    """
    Body an SMS gateway webhook forwards for an inbound message (shape is
    provider-agnostic - Twilio/Exotel/etc. all reduce to "from this phone
    number, this text arrived"; see services/telephony.py's simulator for a
    local stand-in that needs no real account).
    """

    from_phone: str = Field(..., min_length=5, max_length=20)
    body: str = Field(..., min_length=1, max_length=320)


class SmsInboundResponse(BaseModel):
    reply_text: str = Field(..., description="What gets sent back to the farmer's phone - kept SMS-length.")
    understood: bool
