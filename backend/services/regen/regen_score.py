"""
STEP 3 - the Regeneration Score Engine.

Dynamic and explainable, not a static average: a fixed weighted sum of five
sub-scores, each pulled directly from the module that computed it (single
source of truth - see the `*_score` fields each M1-M5 module already
writes into its own `details`), plus the per-field confidence breakdown the
Feature Resolver tagged all the way back at the start of the pipeline.
"""

from __future__ import annotations

from typing import Any

from models.schemas import FarmInput, RegenerationScore
from services.regen.feature_resolver import EnrichedFeatureVector

WEIGHTS = {
    "carbon_trend_score": 0.25,  # from M2
    "fertilizer_efficiency": 0.25,  # from M3
    "rotation_health": 0.20,  # from M1
    "cover_crop_diversity": 0.15,  # from M4
    "water_efficiency": 0.15,  # from M5
}


def compute_regeneration_score(
    farm_input: FarmInput,
    vector: EnrichedFeatureVector,
    m1_details: dict[str, Any],
    m2_details: dict[str, Any],
    m3_details: dict[str, Any],
    m4_details: dict[str, Any],
    m5_details: dict[str, Any],
) -> RegenerationScore:
    rotation_suggestions = m1_details.get("next_crop_suggestions") or []
    rotation_health = rotation_suggestions[0]["score"] if rotation_suggestions else 0.0

    carbon_trend_score = m2_details.get("soil_health_score") or 0.0
    fertilizer_efficiency = m3_details.get("reduction_efficiency_score") or 0.0
    cover_crop_diversity = m4_details.get("diversity_score") or 0.0
    water_efficiency = m5_details.get("water_efficiency_score") or 0.0

    sub_scores = {
        "carbon_trend_score": carbon_trend_score,
        "fertilizer_efficiency": fertilizer_efficiency,
        "rotation_health": rotation_health,
        "cover_crop_diversity": cover_crop_diversity,
        "water_efficiency": water_efficiency,
    }

    score = sum(sub_scores[key] * weight for key, weight in WEIGHTS.items())
    score = round(max(0.0, min(100.0, score)), 1)

    confidence: str = "High" if farm_input.soil_test_available else "Estimated"

    breakdown = {
        "weights": WEIGHTS,
        "sub_scores": {k: round(v, 1) for k, v in sub_scores.items()},
        "weighted_contributions": {
            key: round(sub_scores[key] * weight, 2) for key, weight in WEIGHTS.items()
        },
        "data_confidence": vector.data_confidence,
    }

    return RegenerationScore(score=score, confidence=confidence, breakdown=breakdown)  # type: ignore[arg-type]
