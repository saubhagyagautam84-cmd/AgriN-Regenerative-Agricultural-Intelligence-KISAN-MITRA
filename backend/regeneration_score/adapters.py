"""
Per-module adapters - the ONLY place that knows how to read M1-M5's actual
`ModuleResponse.details` shapes. The engine itself (score_engine.py) never
touches module-specific keys; it only ever sees the standardized shape
these adapters produce:

    {"module": "M1_rotation", "raw_score": 78, "raw_min": 0, "raw_max": 100,
     "confidence_source": "observed"}

`confidence_source` traces back to services/regen/feature_resolver.py's
per-field `.source` tags (farmer_entered / soil_health_card_exact /
soil_health_card_district / soil_health_card_state / crop_standard_default)
- it is read from there, never reinvented here. Each module's
confidence_source is the WORST (least certain) tier among the specific
fields that module actually depends on, e.g. M2 depends on all 5 soil
values, so it's as confident as its shakiest one.
"""

from __future__ import annotations

from typing import Any

from regeneration_score.normalizer import normalize_score
from services.regen.feature_resolver import EnrichedFeatureVector

# Ordered worst -> best, matching confidence.py's CONFIDENCE_MULTIPLIER tiers.
_TIER_RANK = {"estimated": 0, "district_avg": 1, "observed": 2}


def _source_to_tier(source: str) -> str:
    """Map a Feature Resolver ResolvedField.source string to a 3-tier confidence_source."""
    if source in ("farmer_entered", "soil_health_card_exact"):
        return "observed"
    if source in ("soil_health_card_district", "soil_health_card_state"):
        return "district_avg"
    return "estimated"  # crop_standard_default


def _worst_tier(*tiers: str) -> str:
    return min(tiers, key=lambda t: _TIER_RANK[t])


def _binary_tier(is_observed: bool) -> str:
    """For fields with no district-average concept (weather, crop_reference, location)."""
    return "observed" if is_observed else "estimated"


def _module_confidence_sources(vector: EnrichedFeatureVector) -> dict[str, str]:
    """One confidence_source per module, derived from the specific Feature Resolver fields it reads."""
    soil = vector.soil
    aggregated = vector.aggregated

    crop_ref = _binary_tier(aggregated.crop_reference is not None)
    weather = _binary_tier(aggregated.weather is not None)

    soil_npk_ph = _worst_tier(
        _source_to_tier(soil.n_kg_per_ha.source),
        _source_to_tier(soil.p_kg_per_ha.source),
        _source_to_tier(soil.k_kg_per_ha.source),
        _source_to_tier(soil.ph.source),
    )
    soil_all_five = _worst_tier(soil_npk_ph, _source_to_tier(soil.organic_carbon_pct.source))
    soil_organic_carbon = _source_to_tier(soil.organic_carbon_pct.source)

    return {
        # M1 rotation reweights on M2's soil-derived severity, plus needs the crop table.
        "M1_rotation": _worst_tier(crop_ref, soil_all_five),
        # M2 soil carbon reads all 5 soil measurements directly.
        "M2_soil_carbon": soil_all_five,
        # M3 fertilizer reads soil N/P/K/pH + the crop table + weather (ET0).
        "M3_fertilizer": _worst_tier(crop_ref, soil_npk_ph, weather),
        # M4 cover cropping's KNN reads organic carbon + the crop table.
        "M4_cover_crop": _worst_tier(crop_ref, soil_organic_carbon),
        # M5 irrigation reads weather + the crop table (for baseline irrigation count).
        "M5_irrigation": _worst_tier(weather, crop_ref),
    }


def adapt_m1_rotation(details: dict[str, Any], vector: EnrichedFeatureVector) -> dict[str, Any]:
    suggestions = details.get("next_crop_suggestions") or []
    raw_score = suggestions[0]["score"] if suggestions else 0.0
    return {
        "module": "M1_rotation",
        "raw_score": normalize_score(raw_score, 0, 100),  # already 0-100; normalized anyway, never hand-scaled
        "raw_min": 0,
        "raw_max": 100,
        "confidence_source": _module_confidence_sources(vector)["M1_rotation"],
    }


def adapt_m2_soil_carbon(details: dict[str, Any], vector: EnrichedFeatureVector) -> dict[str, Any]:
    raw_score = details.get("soil_health_score") or 0.0
    return {
        "module": "M2_soil_carbon",
        "raw_score": normalize_score(raw_score, 0, 100),
        "raw_min": 0,
        "raw_max": 100,
        "confidence_source": _module_confidence_sources(vector)["M2_soil_carbon"],
    }


def adapt_m3_fertilizer(details: dict[str, Any], vector: EnrichedFeatureVector) -> dict[str, Any]:
    raw_score = details.get("reduction_efficiency_score") or 0.0
    return {
        "module": "M3_fertilizer",
        "raw_score": normalize_score(raw_score, 0, 100),
        "raw_min": 0,
        "raw_max": 100,
        "confidence_source": _module_confidence_sources(vector)["M3_fertilizer"],
    }


def adapt_m4_cover_crop(details: dict[str, Any], vector: EnrichedFeatureVector) -> dict[str, Any]:
    raw_score = details.get("diversity_score") or 0.0
    return {
        "module": "M4_cover_crop",
        "raw_score": normalize_score(raw_score, 0, 100),
        "raw_min": 0,
        "raw_max": 100,
        "confidence_source": _module_confidence_sources(vector)["M4_cover_crop"],
    }


def adapt_m5_irrigation(details: dict[str, Any], vector: EnrichedFeatureVector) -> dict[str, Any]:
    # M5's own module (services/regen/m5_irrigation.py) already converts the
    # raw "liters saved" into a 0-100 efficiency score RELATIVE TO a naive
    # fixed-schedule baseline (see water_efficiency_score there) - that IS
    # the "regional baseline" normalization the spec calls for, computed
    # once where the baseline logic already lives rather than duplicated
    # here. This adapter still routes it through normalize_score so every
    # module's raw_score - regardless of whether it needed scaling - passes
    # through the same shared function, per the no-hand-rolling rule.
    raw_score = details.get("water_efficiency_score") or 0.0
    return {
        "module": "M5_irrigation",
        "raw_score": normalize_score(raw_score, 0, 100),
        "raw_min": 0,
        "raw_max": 100,
        "confidence_source": _module_confidence_sources(vector)["M5_irrigation"],
    }


def adapt_all_modules(
    vector: EnrichedFeatureVector,
    m1_details: dict[str, Any],
    m2_details: dict[str, Any],
    m3_details: dict[str, Any],
    m4_details: dict[str, Any],
    m5_details: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Every module's ModuleResponse.details -> the standardized input shape, keyed by module name."""
    return {
        "M1_rotation": adapt_m1_rotation(m1_details, vector),
        "M2_soil_carbon": adapt_m2_soil_carbon(m2_details, vector),
        "M3_fertilizer": adapt_m3_fertilizer(m3_details, vector),
        "M4_cover_crop": adapt_m4_cover_crop(m4_details, vector),
        "M5_irrigation": adapt_m5_irrigation(m5_details, vector),
    }
