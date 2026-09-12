"""
MODULE 2 - Soil Carbon / Health Tracker.

Built in two phases because of the cross-module dependency the spec
requires:

    Phase A `compute_severity()` runs FIRST, right after the Feature
    Resolver. It only needs soil data, and its output (soil-depletion
    `severity`) is what M1 (rotation) reads to decide how hard to push
    nitrogen-fixing legumes.

    Phase B `run()` runs LAST, after M1 and M4 have already produced their
    picks, because the "regenerative practice" trend line needs to know
    whether the rotation plan includes a legume and how many cover crops
    M4 suggested.

Reads : EnrichedFeatureVector.soil (+ M1's rotation details, M4's cover-crop
        details for the trend projection)
Writes: ModuleResponse(module_name="soil_health")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from models.schemas import ModuleResponse
from services.modules.common import SHC_RATING_BANDS, rate_nutrient
from services.regen.feature_resolver import EnrichedFeatureVector

MODULE_NAME = "soil_health"

# Numeric score assigned to each SHC low/medium/high rating band.
RATING_SCORE: dict[str, float] = {"low": 40.0, "medium": 75.0, "high": 100.0}

SEVERITY_THRESHOLDS = {"severe": 40.0, "moderate": 70.0}  # score < severe -> "severe", etc.

# Season-over-season soil organic carbon decline under continued
# mono-cropping / no organic inputs. Illustrative rates from general
# soil-science literature on continuous cultivation without residue
# return or legume rotation - NOT measured for this specific field.
# Verify against local long-term trial data before real deployment.
DECLINE_RATE_PER_SEASON = 0.07  # -7% per season, current practice

# Improvement rate under a regenerative practice (legume in rotation +
# cover cropping), before the M1/M4-driven bonus below is added.
BASE_IMPROVEMENT_RATE_PER_SEASON = 0.04  # +4% per season, baseline regen practice
LEGUME_BONUS_PER_SEASON = 0.03  # extra, if M1's plan includes a legume next
COVER_CROP_BONUS_PER_SEASON = 0.015  # extra, per distinct M4 cover-crop suggestion (capped)
MAX_COVER_CROP_BONUS_STEPS = 2


@dataclass
class SeverityResult:
    soil_health_score: float  # 0-100
    severity: str  # "low" | "moderate" | "severe"
    flag: str


def _ph_score(ph: Optional[float]) -> float:
    if ph is None:
        return 60.0
    if 6.5 <= ph <= 7.5:
        return 100.0
    if 5.5 <= ph < 6.5 or 7.5 < ph <= 8.5:
        return 75.0
    return 40.0


def compute_severity(vector: EnrichedFeatureVector) -> SeverityResult:
    """Phase A. Only needs soil data - safe to call before M1 runs."""
    soil = vector.soil

    n_score = RATING_SCORE.get(rate_nutrient("n_kg_per_ha", soil.n_kg_per_ha.value) or "medium", 75.0)
    p_score = RATING_SCORE.get(rate_nutrient("p_kg_per_ha", soil.p_kg_per_ha.value) or "medium", 75.0)
    k_score = RATING_SCORE.get(rate_nutrient("k_kg_per_ha", soil.k_kg_per_ha.value) or "medium", 75.0)
    oc_score = RATING_SCORE.get(
        rate_nutrient("organic_carbon_pct", soil.organic_carbon_pct.value) or "medium", 75.0
    )
    ph_score = _ph_score(soil.ph.value)

    score = round((n_score + p_score + k_score + oc_score + ph_score) / 5, 1)

    if score < SEVERITY_THRESHOLDS["severe"]:
        severity = "severe"
        flag = "Soil is severely depleted - prioritise nitrogen-fixing legumes and organic matter now."
    elif score < SEVERITY_THRESHOLDS["moderate"]:
        severity = "moderate"
        flag = "Soil health is moderate - a legume break crop and residue return would help."
    else:
        severity = "low"
        flag = "Soil is in reasonably good health - you have flexibility in what to grow next."

    return SeverityResult(soil_health_score=score, severity=severity, flag=flag)


def _trend_projection(
    base_score: float,
    rotation_has_legume: bool,
    cover_crop_count: int,
) -> dict[str, list[dict[str, Any]]]:
    """The two data series for a diverging-lines chart, 3 seasons ahead."""
    cover_steps = min(cover_crop_count, MAX_COVER_CROP_BONUS_STEPS)
    improve_rate = (
        BASE_IMPROVEMENT_RATE_PER_SEASON
        + (LEGUME_BONUS_PER_SEASON if rotation_has_legume else 0.0)
        + COVER_CROP_BONUS_PER_SEASON * cover_steps
    )

    current_practice: list[dict[str, Any]] = []
    regenerative_practice: list[dict[str, Any]] = []
    current_value = base_score
    regen_value = base_score
    for season in range(1, 4):
        current_value = round(max(0.0, current_value * (1 - DECLINE_RATE_PER_SEASON)), 1)
        regen_value = round(min(100.0, regen_value * (1 + improve_rate)), 1)
        current_practice.append({"season": season, "soil_health_score": current_value})
        regenerative_practice.append({"season": season, "soil_health_score": regen_value})

    return {"current_practice": current_practice, "regenerative_practice": regenerative_practice}


def run(
    vector: EnrichedFeatureVector,
    severity: SeverityResult,
    rotation_details: dict[str, Any],
    cover_details: dict[str, Any],
) -> ModuleResponse:
    """Phase B. Combines the Phase A severity with M1/M4's picks for the trend."""
    plan = rotation_details.get("next_crop_suggestions") or []
    rotation_has_legume = any(entry.get("is_legume") for entry in plan)
    cover_crop_count = len(cover_details.get("cover_crop_suggestions") or [])

    projection = _trend_projection(severity.soil_health_score, rotation_has_legume, cover_crop_count)

    gap_3_season = round(
        projection["regenerative_practice"][-1]["soil_health_score"]
        - projection["current_practice"][-1]["soil_health_score"],
        1,
    )
    trend = (
        f"Under current practice, soil health is projected to fall to "
        f"{projection['current_practice'][-1]['soil_health_score']} by season 3. "
        f"Following the rotation + cover-crop plan below, it could instead reach "
        f"{projection['regenerative_practice'][-1]['soil_health_score']} "
        f"(a {gap_3_season:+.1f}-point gap)."
    )

    summary = f"Soil health score {severity.soil_health_score}/100 ({severity.severity} depletion). {severity.flag}"

    details = {
        "soil_health_score": severity.soil_health_score,
        "trend": trend,
        "flag": severity.flag,
        "severity": severity.severity,
        "projection": projection,
        "rating_bands_used": sorted(SHC_RATING_BANDS.keys() & {"n_kg_per_ha", "p_kg_per_ha", "k_kg_per_ha", "organic_carbon_pct"}),
        "data_sources": {
            "n_kg_per_ha": vector.soil.n_kg_per_ha.source,
            "p_kg_per_ha": vector.soil.p_kg_per_ha.source,
            "k_kg_per_ha": vector.soil.k_kg_per_ha.source,
            "ph": vector.soil.ph.source,
            "organic_carbon_pct": vector.soil.organic_carbon_pct.source,
        },
        "assumptions": (
            f"Current-practice decline modelled at -{DECLINE_RATE_PER_SEASON*100:.0f}%/season "
            "(continuous cultivation, no organic return) - a general soil-science pattern, not "
            "measured for this field. Regenerative improvement rate scales with whether the M1 "
            "rotation plan includes a legume and how many M4 cover crops are suggested."
        ),
        "is_dummy_data": True,
    }

    status = "ok" if severity.severity != "severe" else "partial"
    if status == "ok":
        return ModuleResponse.ok(MODULE_NAME, summary, details, confidence=None)
    return ModuleResponse.partial(MODULE_NAME, summary, details, confidence=None)
