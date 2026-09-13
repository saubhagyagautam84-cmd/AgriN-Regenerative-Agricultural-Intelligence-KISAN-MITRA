"""
STEP 1 (Part B) - the Feature Resolver.

Its only job: never let missing data block a prediction. Part A's
AggregatedData already resolves location/weather/crop with graceful
degradation (see services/aggregator.py) - this module adds the Part B
specific resolution on top of it:

    * soil, via the Geographic Confidence Ladder (see
      services/regen/geo_resolvers.py) - farmer's manual entry first, then
      block/village -> district -> state -> national Soil Health Card
      averages, never the flat "district or nothing" resolution Part A's
      own soil_status module uses (that one stays simple on purpose - this
      is Part B/C's own, more granular resolution for the Regeneration
      Score specifically)
    * the crop-photo health score (or a baseline default if no photo)

Every resolved field is tagged with one of the 6 geographic confidence
levels in `data_confidence` (see regeneration_score/confidence.py's
GEOGRAPHIC_CONFIDENCE_MULTIPLIER) - that flag flows all the way through to
the final Regeneration Score's confidence breakdown. Nothing in here ever
raises; anything unavailable falls back to a documented default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from models.schemas import AggregatedData, FarmInput
from services.regen.geo_resolvers import resolve_soil_field

# Crop-standard "textbook" mid-band default - the ladder's own true floor
# (below even "national_avg"): used only when NEITHER the farmer's manual
# entry NOR any Soil Health Card record anywhere in the dataset is
# available, i.e. resolve_soil_field couldn't produce a real value at all.
# Values are the low/medium boundary of the Government SHC rating bands
# (see services/modules/common.py SHC_RATING_BANDS) - i.e. "assume
# just-adequate" rather than guessing high or low. Still tagged
# "national_avg" (the ladder's lowest real rung) rather than inventing a
# 7th tier for this rare edge case.
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
    source: str  # human-readable trace, e.g. "your own soil test" / "Ludhiana district average (2 samples)"
    confidence: str  # one of the 6 geographic confidence levels - see confidence.py


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
    confidence: str  # "observed" | "national_avg" (no geography involved - see resolve_crop_health)
    note: Optional[str] = None


@dataclass
class EnrichedFeatureVector:
    """The one object every Part B module reads."""

    aggregated: AggregatedData
    soil: ResolvedSoil
    crop_health: ResolvedCropHealth
    data_confidence: dict[str, str] = field(default_factory=dict)


def _resolve_one(pin_code: Optional[str], field_name: str, manual_value: Optional[float], default_value: float) -> ResolvedField:
    resolved = resolve_soil_field(pin_code, field_name, manual_value)
    if resolved.value is not None:
        return ResolvedField(resolved.value, resolved.detail, resolved.confidence_level)
    # resolve_soil_field only returns value=None when the entire dataset has
    # no usable record anywhere (not just this farm's location) - the true
    # ladder floor, below which only the crop-standard default remains.
    return ResolvedField(default_value, "no Soil Health Card data anywhere - crop-standard default assumed", "national_avg")


def resolve_soil(farm_input: FarmInput, aggregated: AggregatedData) -> ResolvedSoil:
    pin_code = aggregated.location.pincode if aggregated.location else farm_input.pincode

    return ResolvedSoil(
        n_kg_per_ha=_resolve_one(pin_code, "n_kg_per_ha", farm_input.soil_test_n_kg_per_ha, CROP_STANDARD_SOIL_DEFAULT["n_kg_per_ha"]),
        p_kg_per_ha=_resolve_one(pin_code, "p_kg_per_ha", farm_input.soil_test_p_kg_per_ha, CROP_STANDARD_SOIL_DEFAULT["p_kg_per_ha"]),
        k_kg_per_ha=_resolve_one(pin_code, "k_kg_per_ha", farm_input.soil_test_k_kg_per_ha, CROP_STANDARD_SOIL_DEFAULT["k_kg_per_ha"]),
        ph=_resolve_one(pin_code, "ph", farm_input.soil_test_ph, CROP_STANDARD_SOIL_DEFAULT["ph"]),
        organic_carbon_pct=_resolve_one(
            pin_code, "organic_carbon_pct", farm_input.soil_test_organic_carbon_pct, CROP_STANDARD_SOIL_DEFAULT["organic_carbon_pct"]
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
        # No photo, no geography to fall back through (a photo isn't
        # something a block/district/state "average" could stand in for) -
        # this is a straight binary observed/not-observed, tagged at the
        # ladder's floor when absent rather than inventing a 7th tier.
        confidence="national_avg",
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
        "location": "observed" if aggregated.location.resolved else "national_avg",
        "weather": "observed" if aggregated.weather is not None else "national_avg",
        "crop_reference": "observed" if aggregated.crop_reference is not None else "national_avg",
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
