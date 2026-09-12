"""
MODULE 1 - Crop Rotation Advisor.

Reads : EnrichedFeatureVector (crop, sowing/season, location) + M2's Phase A
        `SeverityResult` - the required cross-module dependency: severely
        depleted soil prioritises nitrogen-fixing legumes hard; healthy soil
        allows cash-crop flexibility (season/rotation fit weighted more,
        legume bonus weighted less).
Writes: ModuleResponse(module_name="rotation") with
        details = {"next_crop_suggestions": [...], "reason": "..."}
"""

from __future__ import annotations

from typing import Any

from models.schemas import ModuleResponse
from services import data_loader
from services.modules.common import SEASON_LABELS, as_value, next_season
from services.regen.feature_resolver import EnrichedFeatureVector
from services.regen.m2_soil_carbon import SeverityResult

MODULE_NAME = "rotation"
MAX_SUGGESTIONS = 3

# How hard the legume bonus is weighted, by M2's severity bucket - this is
# the reweighting the spec requires: severe soil pushes legumes hard,
# healthy soil relaxes it so cash-crop flexibility can compete on other
# factors.
LEGUME_WEIGHT_BY_SEVERITY = {"severe": 50.0, "moderate": 30.0, "low": 12.0}
# Heavy-feeder penalty (per kg/ha of N requirement) applied only when soil
# needs to recover - discourages piling a nutrient-hungry crop onto tired soil.
HEAVY_FEEDER_PENALTY_PER_N_KG = {"severe": 0.25, "moderate": 0.1, "low": 0.0}


def run(vector: EnrichedFeatureVector, severity: SeverityResult) -> ModuleResponse:
    aggregated = vector.aggregated
    current = aggregated.crop_reference
    _index, all_crops, _report = data_loader.load_crop_reference()

    if current is None or not all_crops:
        return ModuleResponse.partial(
            MODULE_NAME,
            summary=f"'{aggregated.farm_input.crop_name}' is not in our crop guide yet, so we cannot reweight a rotation plan for it.",
            details={
                "next_crop_suggestions": [],
                "reason": "Crop not found in reference table.",
                "is_dummy_data": True,
            },
            confidence=None,
        )

    target_season_enum, season_window = next_season()
    target_season = target_season_enum.value

    preferred_names = set(current.rotation_compatible_with)
    avoid_names = set(current.rotation_avoid) | {current.crop_name}

    legume_weight = LEGUME_WEIGHT_BY_SEVERITY[severity.severity]
    heavy_feeder_penalty = HEAVY_FEEDER_PENALTY_PER_N_KG[severity.severity]

    unhealthy_crop = not vector.crop_health.is_placeholder and vector.crop_health.score < 0.6

    scored: list[dict[str, Any]] = []
    for candidate in all_crops:
        if candidate.crop_name in avoid_names:
            continue
        candidate_season = as_value(candidate.season)
        if candidate_season not in (target_season, "perennial"):
            continue

        score = 0.0
        reasons: list[str] = []

        if candidate.crop_name in preferred_names:
            score += 35
            reasons.append(f"ICAR-recommended rotation after {current.crop_name}")
        else:
            score += 12

        if candidate_season == target_season:
            score += 20
            reasons.append(f"Fits the coming {SEASON_LABELS.get(target_season, target_season)} season")
        else:
            score += 8
            reasons.append("Can be planted year-round")

        if candidate.is_legume:
            score += legume_weight
            reasons.append(
                f"Nitrogen-fixing legume - weighted {'heavily' if severity.severity == 'severe' else 'moderately' if severity.severity == 'moderate' else 'lightly'} "
                f"given your soil's {severity.severity} depletion"
            )
            if unhealthy_crop:
                score += 10
                reasons.append("Extra weight: current crop's photo health check flagged stress")

        score -= candidate.n_requirement_kg_per_ha * heavy_feeder_penalty

        scored.append(
            {
                "crop_name": candidate.crop_name,
                "local_name": candidate.local_names.get("hi"),
                "is_legume": candidate.is_legume,
                "score": round(max(0.0, min(100.0, score)), 1),
                "season": candidate_season,
                "season_label": SEASON_LABELS.get(candidate_season, candidate_season),
                "n_requirement_kg_per_ha": candidate.n_requirement_kg_per_ha,
                "water_requirement_mm": candidate.water_requirement_mm,
                "reasons": reasons,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    top = scored[:MAX_SUGGESTIONS]

    if not top:
        return ModuleResponse.partial(
            MODULE_NAME,
            summary=f"No suitable {SEASON_LABELS.get(target_season, target_season)} rotation crop found after {current.crop_name}.",
            details={
                "next_crop_suggestions": [],
                "reason": "No candidate crop in the reference table matched the coming season and avoid-list.",
                "is_dummy_data": True,
            },
            confidence=None,
        )

    reason = (
        f"Soil-depletion severity from M2 is '{severity.severity}' (score {severity.soil_health_score}/100), "
        f"so legume suggestions were weighted {legume_weight:.0f}/100 "
        f"{'(strong push toward nitrogen-fixers)' if severity.severity == 'severe' else '(cash-crop flexibility allowed)' if severity.severity == 'low' else '(moderate push)'}, "
        f"then ranked by ICAR rotation compatibility with {current.crop_name} and season fit."
    )

    best = top[0]
    local = f" ({best['local_name']})" if best["local_name"] else ""
    summary = f"After {current.crop_name}, {best['crop_name']}{local} is the top rotation pick for {SEASON_LABELS.get(target_season, target_season)}."

    details = {
        "current_crop": current.crop_name,
        "season_window": season_window,
        "severity_used": severity.severity,
        "next_crop_suggestions": top,
        "reason": reason,
        "avoid": sorted(current.rotation_avoid),
        "is_dummy_data": True,
    }
    return ModuleResponse.ok(MODULE_NAME, summary, details, confidence=None)
