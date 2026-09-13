"""
Per-module adapters - the ONLY place that knows how to read M1-M5's actual
`ModuleResponse.details` shapes. The engine itself (score_engine.py) never
touches module-specific keys; it only ever sees the standardized shape
these adapters produce:

    {"module": "M1_rotation", "raw_score": 78, "raw_min": 0, "raw_max": 100,
     "confidence_source": "observed", "confidence_detail": "your own soil test"}

`confidence_source` is one of the 6 Geographic Confidence Ladder levels
(regeneration_score/confidence.py's GEOGRAPHIC_CONFIDENCE_MULTIPLIER).
`confidence_detail` is the human-readable trace behind it (e.g. "Ludhiana
district average (2 samples)"), surfaced on the dashboard per-module rather
than a bare tier name - see score_engine.py's breakdown and
components/RegenScoreCard.tsx.

Soil fields trace back to services/regen/feature_resolver.py's per-field
`.confidence`/`.source` tags (from services/regen/geo_resolvers.py's
resolve_soil_field); the crop table's confidence comes from that same
module's resolve_crop_suitability - two SEPARATE resolution chains, read
here, never reinvented (see geo_resolvers.py's module docstring for why
they aren't merged). Each module's confidence is the WORST (least certain)
tier among the specific fields that module actually depends on, e.g. M2
depends on all 5 soil values, so it's as confident as its shakiest one -
and it carries THAT field's own detail string, not a generic one.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from regeneration_score.confidence import GEO_CONFIDENCE_RANK
from regeneration_score.normalizer import normalize_score
from services.regen.feature_resolver import EnrichedFeatureVector
from services.regen.geo_resolvers import resolve_crop_suitability


class ConfidenceTag(NamedTuple):
    level: str  # one of the 6 Geographic Confidence Ladder levels
    detail: str  # human-readable trace, e.g. "Ludhiana district average (2 samples)"


def _worst(*tags: ConfidenceTag) -> ConfidenceTag:
    return min(tags, key=lambda tag: GEO_CONFIDENCE_RANK[tag.level])


def _binary_tag(is_observed: bool, observed_detail: str, missing_detail: str) -> ConfidenceTag:
    """For fields with no geographic-average concept at all (weather) - see feature_resolver.py."""
    return ConfidenceTag("observed", observed_detail) if is_observed else ConfidenceTag("national_avg", missing_detail)


def _module_confidence_tags(vector: EnrichedFeatureVector) -> dict[str, ConfidenceTag]:
    """One (level, detail) tag per module, derived from the specific Feature Resolver fields it reads."""
    soil = vector.soil
    aggregated = vector.aggregated
    pin_code = aggregated.location.pincode if aggregated.location else None

    # Crop suitability's OWN resolution chain (zone_baseline by default,
    # upgraded to district_avg with real local signal) - not the soil
    # ladder, and not a binary observed/not-observed check.
    suitability = resolve_crop_suitability(pin_code)
    crop_ref = ConfidenceTag(suitability.confidence_level, suitability.detail)
    weather = _binary_tag(
        aggregated.weather is not None, "live Open-Meteo forecast", "weather data unavailable"
    )

    n = ConfidenceTag(soil.n_kg_per_ha.confidence, soil.n_kg_per_ha.source)
    p = ConfidenceTag(soil.p_kg_per_ha.confidence, soil.p_kg_per_ha.source)
    k = ConfidenceTag(soil.k_kg_per_ha.confidence, soil.k_kg_per_ha.source)
    ph = ConfidenceTag(soil.ph.confidence, soil.ph.source)
    oc = ConfidenceTag(soil.organic_carbon_pct.confidence, soil.organic_carbon_pct.source)

    soil_npk_ph = _worst(n, p, k, ph)
    soil_all_five = _worst(soil_npk_ph, oc)

    return {
        # M1 rotation reweights on M2's soil-derived severity, plus needs the crop table.
        "M1_rotation": _worst(crop_ref, soil_all_five),
        # M2 soil carbon reads all 5 soil measurements directly.
        "M2_soil_carbon": soil_all_five,
        # M3 fertilizer reads soil N/P/K/pH + the crop table + weather (ET0).
        "M3_fertilizer": _worst(crop_ref, soil_npk_ph, weather),
        # M4 cover cropping's KNN reads organic carbon + the crop table.
        "M4_cover_crop": _worst(crop_ref, oc),
        # M5 irrigation reads weather + the crop table (for baseline irrigation count).
        "M5_irrigation": _worst(weather, crop_ref),
    }


def _base_entry(module: str, raw_score: float, tag: ConfidenceTag) -> dict[str, Any]:
    return {
        "module": module,
        "raw_score": normalize_score(raw_score, 0, 100),
        "raw_min": 0,
        "raw_max": 100,
        "confidence_source": tag.level,
        "confidence_detail": tag.detail,
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
    tags = _module_confidence_tags(vector)

    m1_suggestions = m1_details.get("next_crop_suggestions") or []
    m1_raw = m1_suggestions[0]["score"] if m1_suggestions else 0.0

    return {
        "M1_rotation": _base_entry("M1_rotation", m1_raw, tags["M1_rotation"]),
        "M2_soil_carbon": _base_entry("M2_soil_carbon", m2_details.get("soil_health_score") or 0.0, tags["M2_soil_carbon"]),
        "M3_fertilizer": _base_entry("M3_fertilizer", m3_details.get("reduction_efficiency_score") or 0.0, tags["M3_fertilizer"]),
        "M4_cover_crop": _base_entry("M4_cover_crop", m4_details.get("diversity_score") or 0.0, tags["M4_cover_crop"]),
        # M5's own module (services/regen/m5_irrigation.py) already converts
        # the raw "liters saved" into a 0-100 efficiency score RELATIVE TO a
        # naive fixed-schedule baseline (see water_efficiency_score there) -
        # that IS the "regional baseline" normalization the spec calls for,
        # computed once where the baseline logic already lives rather than
        # duplicated here.
        "M5_irrigation": _base_entry("M5_irrigation", m5_details.get("water_efficiency_score") or 0.0, tags["M5_irrigation"]),
    }
