"""
STEP 1 (Part B) - the Feature Resolver.

Its only job: never let missing data block a prediction. Part A's
AggregatedData already resolves location/soil/weather/crop with graceful
degradation (see services/aggregator.py) - this module adds the Part B
specific resolution on top of it:

    * precedence between the farmer's manually-entered soil test values and
      the Soil Health Card lookup Part A already did
    * the crop-photo health score (or a baseline default if no photo)

Every resolved field is tagged "observed" or "estimated" in
`data_confidence` - that flag flows all the way through to the final
Regeneration Score's confidence breakdown (see regen_score.py). Nothing in
here ever raises; anything unavailable falls back to a documented default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from models.schemas import AggregatedData, FarmInput

# Crop-standard "textbook" mid-band defaults - used only when NEITHER the
# farmer's manual entry NOR any Soil Health Card record is available. Values
# are the low/medium boundary of the Government SHC rating bands (see
# services/modules/common.py SHC_RATING_BANDS) - i.e. "assume just-adequate"
# rather than guessing high or low.
CROP_STANDARD_SOIL_DEFAULT: dict[str, float] = {
    "n_kg_per_ha": 280.0,
    "p_kg_per_ha": 17.0,
    "k_kg_per_ha": 150.0,
    "ph": 6.8,
    "organic_carbon_pct": 0.55,
}


@dataclass
class ResolvedField:
    value: float
    source: str  # "farmer_entered" | "soil_health_card_<level>" | "crop_standard_default"
    confidence: str  # "observed" | "estimated"


@dataclass
class ResolvedSoil:
    n_kg_per_ha: ResolvedField
    p_kg_per_ha: ResolvedField
    k_kg_per_ha: ResolvedField
    ph: ResolvedField
    organic_carbon_pct: ResolvedField


@dataclass
class ResolvedCropHealth:
    score: float
    is_placeholder: bool
    source: str  # "cnn" | "baseline_default"
    confidence: str  # "observed" | "estimated"
    note: Optional[str] = None


@dataclass
class EnrichedFeatureVector:
    """The one object every Part B module reads."""

    aggregated: AggregatedData
    soil: ResolvedSoil
    crop_health: ResolvedCropHealth
    data_confidence: dict[str, str] = field(default_factory=dict)


def _resolve_one(
    manual_value: Optional[float],
    shc_value: Optional[float],
    shc_match_level: str,
    default_value: float,
) -> ResolvedField:
    if manual_value is not None:
        return ResolvedField(manual_value, "farmer_entered", "observed")
    if shc_value is not None:
        if shc_match_level == "exact_pincode":
            return ResolvedField(shc_value, "soil_health_card_exact", "observed")
        # A district/state average is a real number, just not THIS field's soil.
        return ResolvedField(shc_value, f"soil_health_card_{shc_match_level}", "estimated")
    return ResolvedField(default_value, "crop_standard_default", "estimated")


def resolve_soil(farm_input: FarmInput, aggregated: AggregatedData) -> ResolvedSoil:
    soil = aggregated.soil
    match_level = soil.match_level if soil else "none"

    return ResolvedSoil(
        n_kg_per_ha=_resolve_one(
            farm_input.soil_test_n_kg_per_ha,
            soil.n_kg_per_ha if soil else None,
            match_level,
            CROP_STANDARD_SOIL_DEFAULT["n_kg_per_ha"],
        ),
        p_kg_per_ha=_resolve_one(
            farm_input.soil_test_p_kg_per_ha,
            soil.p_kg_per_ha if soil else None,
            match_level,
            CROP_STANDARD_SOIL_DEFAULT["p_kg_per_ha"],
        ),
        k_kg_per_ha=_resolve_one(
            farm_input.soil_test_k_kg_per_ha,
            soil.k_kg_per_ha if soil else None,
            match_level,
            CROP_STANDARD_SOIL_DEFAULT["k_kg_per_ha"],
        ),
        ph=_resolve_one(
            farm_input.soil_test_ph,
            soil.ph if soil else None,
            match_level,
            CROP_STANDARD_SOIL_DEFAULT["ph"],
        ),
        organic_carbon_pct=_resolve_one(
            farm_input.soil_test_organic_carbon_pct,
            soil.organic_carbon_pct if soil else None,
            match_level,
            CROP_STANDARD_SOIL_DEFAULT["organic_carbon_pct"],
        ),
    )


def resolve_crop_health(farm_input: FarmInput) -> ResolvedCropHealth:
    if farm_input.crop_health_score is not None:
        return ResolvedCropHealth(
            score=farm_input.crop_health_score,
            is_placeholder=False,
            source="cnn",
            confidence="observed",
        )
    return ResolvedCropHealth(
        score=1.0,
        is_placeholder=True,
        source="baseline_default",
        confidence="estimated",
        note="No crop photo was provided - baseline health (1.0) assumed.",
    )


def build_enriched_feature_vector(
    farm_input: FarmInput, aggregated: AggregatedData
) -> EnrichedFeatureVector:
    """The single call site for the whole Feature Resolver stage."""
    soil = resolve_soil(farm_input, aggregated)
    crop_health = resolve_crop_health(farm_input)

    data_confidence = {
        "n_kg_per_ha": soil.n_kg_per_ha.confidence,
        "p_kg_per_ha": soil.p_kg_per_ha.confidence,
        "k_kg_per_ha": soil.k_kg_per_ha.confidence,
        "ph": soil.ph.confidence,
        "organic_carbon_pct": soil.organic_carbon_pct.confidence,
        "crop_health": crop_health.confidence,
        "location": "observed" if aggregated.location.resolved else "estimated",
        "weather": "observed" if aggregated.weather is not None else "estimated",
        "crop_reference": "observed" if aggregated.crop_reference is not None else "estimated",
        # sowing_date and irrigation_source (water_source) have no
        # "missing -> estimate" fallback path, unlike everything else here -
        # deliberately, not an oversight. sowing_date is a required field and
        # irrigation_source defaults to "rainfed" in the form contract
        # itself (see models/schemas.py::FarmInput), so there is never a
        # "missing" case for this resolver to catch. See
        # scripts/generate_field_spec.py's note on this for the full reasoning.
        "sowing_date": "observed",
        "irrigation_source": "observed",
    }

    return EnrichedFeatureVector(
        aggregated=aggregated,
        soil=soil,
        crop_health=crop_health,
        data_confidence=data_confidence,
    )
