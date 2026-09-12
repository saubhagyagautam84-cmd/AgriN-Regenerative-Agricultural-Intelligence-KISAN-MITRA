"""
MODULE 4 - Cover-Cropping / Intercropping Advisor.

Reads : EnrichedFeatureVector (crop -> its cover_crops list from
        crop_reference.json, irrigation capacity, soil organic carbon)
Writes: ModuleResponse(module_name="cover_cropping") with
        details = {"cover_crop_suggestions": [...], "benefit": "..."}

Base ranking is a rule-based lookup against crop_reference.json's
`cover_crops` list (see data/crop_reference.json cover_crops_note - general
ICAR/KVK green-manuring recommendations). The REQUIRED "advanced layer" is a
KNN ranking on top of that: a KNeighborsClassifier trained on a small
SYNTHETIC "similar farm profiles" dataset (generated below, not real farm
records - none exist yet) orders suggestion #1 vs #2 by whether farms like
this one tend to benefit more from a fast nitrogen-fixing cover crop or a
slower companion/trap crop.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.neighbors import KNeighborsClassifier

from models.schemas import ModuleResponse
from services.modules.common import IRRIGATION_CAPACITY_MM, as_value
from services.regen.feature_resolver import EnrichedFeatureVector

MODULE_NAME = "cover_cropping"

# Rough traits for the cover crops named in crop_reference.json's
# cover_crops lists. n_fixing_speed: "fast" (classic green-manure legumes),
# "medium" (grain legumes also usable as cover), or "none" (non-legume
# companion/trap crop). Illustrative, not a per-variety agronomic trial.
COVER_CROP_TRAITS: dict[str, dict[str, Any]] = {
    "Cowpea": {"n_fixing_speed": "fast", "water_need": "low"},
    "Sunhemp": {"n_fixing_speed": "fast", "water_need": "low"},
    "Dhaincha (Sesbania)": {"n_fixing_speed": "fast", "water_need": "low"},
    "Green Gram": {"n_fixing_speed": "medium", "water_need": "medium"},
    "Black Gram": {"n_fixing_speed": "medium", "water_need": "medium"},
    "Horse Gram": {"n_fixing_speed": "medium", "water_need": "low"},
    "Sesame": {"n_fixing_speed": "none", "water_need": "low"},
    "Mustard": {"n_fixing_speed": "none", "water_need": "low"},
    "Linseed": {"n_fixing_speed": "none", "water_need": "low"},
    "Sorghum (fodder)": {"n_fixing_speed": "none", "water_need": "medium"},
    "Sorghum (border)": {"n_fixing_speed": "none", "water_need": "medium"},
    "Sunflower": {"n_fixing_speed": "none", "water_need": "medium"},
}

_RNG = np.random.default_rng(42)


def _build_synthetic_profiles(n: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """
    SYNTHETIC "similar farm profiles" database. Features:
        [available_water_mm, organic_carbon_pct, is_legume_current_crop]
    Label: 1 if that synthetic farm's better outcome was modelled as a fast
    N-fixing cover crop (true whenever organic carbon is low - the textbook
    reason to reach for a green manure), else 0. A little label noise is
    added so the classifier is not trivially deterministic.
    """
    water = _RNG.uniform(50, 1200, n)
    organic_carbon = _RNG.uniform(0.2, 1.2, n)
    is_legume_current = _RNG.integers(0, 2, n)

    prefers_fast_fixer = (organic_carbon < 0.6).astype(int)
    flip = _RNG.random(n) < 0.08
    prefers_fast_fixer = np.where(flip, 1 - prefers_fast_fixer, prefers_fast_fixer)

    X = np.column_stack([water, organic_carbon, is_legume_current])
    return X, prefers_fast_fixer


_PROFILE_X, _PROFILE_Y = _build_synthetic_profiles()
_KNN = KNeighborsClassifier(n_neighbors=5)
_KNN.fit(_PROFILE_X, _PROFILE_Y)


def run(vector: EnrichedFeatureVector) -> ModuleResponse:
    aggregated = vector.aggregated
    crop = aggregated.crop_reference

    if crop is None or not crop.cover_crops:
        return ModuleResponse.partial(
            MODULE_NAME,
            summary=f"No cover-crop recommendation available for '{aggregated.farm_input.crop_name}' yet.",
            details={"cover_crop_suggestions": [], "benefit": "", "is_dummy_data": True},
            confidence=None,
        )

    source = as_value(aggregated.farm_input.irrigation_source)
    available_water_mm = IRRIGATION_CAPACITY_MM.get(source, 400.0)
    organic_carbon = vector.soil.organic_carbon_pct.value
    is_legume_current = 1 if crop.is_legume else 0

    query = np.array([[available_water_mm, organic_carbon, is_legume_current]])
    proba_fast_fixer = float(_KNN.predict_proba(query)[0][1]) if len(_KNN.classes_) > 1 else float(_KNN.predict(query)[0])

    def rank_key(name: str) -> tuple[float, str]:
        traits = COVER_CROP_TRAITS.get(name, {"n_fixing_speed": "none"})
        is_fast = traits["n_fixing_speed"] == "fast"
        is_medium = traits["n_fixing_speed"] == "medium"
        fixer_bonus = 1.0 if is_fast else 0.5 if is_medium else 0.0
        # When the KNN model favours a fast fixer, sort fixers first;
        # otherwise keep the crop table's own ordering (still ascending name
        # as a stable tiebreak).
        primary = -fixer_bonus if proba_fast_fixer >= 0.5 else 0.0
        return (primary, name)

    ordered_names = sorted(crop.cover_crops, key=rank_key)

    suggestions = []
    for rank, name in enumerate(ordered_names, start=1):
        traits = COVER_CROP_TRAITS.get(name, {"n_fixing_speed": "unknown", "water_need": "unknown"})
        suggestions.append(
            {
                "rank": rank,
                "cover_crop": name,
                "nitrogen_fixing_speed": traits["n_fixing_speed"],
                "water_need": traits.get("water_need", "unknown"),
                "knn_similar_farm_preference": round(proba_fast_fixer, 2),
            }
        )

    top = suggestions[0]
    if top["nitrogen_fixing_speed"] == "fast":
        benefit = (
            f"{top['cover_crop']} fixes nitrogen quickly and covers bare soil between seasons, "
            "cutting erosion and reducing next season's urea need."
        )
    elif top["nitrogen_fixing_speed"] == "medium":
        benefit = f"{top['cover_crop']} adds some nitrogen and ground cover, with a useful grain harvest too."
    else:
        benefit = f"{top['cover_crop']} suppresses weeds and pests as a companion/trap crop, though it does not fix nitrogen."

    summary = f"Best cover crop after {crop.crop_name}: {top['cover_crop']}."

    # 0-100 sub-score for the Regeneration Score Engine: more distinct cover
    # crop options (capped at 3) plus a bonus if the top pick is a fast
    # N-fixer.
    diversity_score = round(min(len(suggestions), 3) / 3 * 80 + (20 if top["nitrogen_fixing_speed"] == "fast" else 0), 1)

    details = {
        "current_crop": crop.crop_name,
        "cover_crop_suggestions": suggestions,
        "benefit": benefit,
        "diversity_score": diversity_score,
        "ranking_method": (
            "Rule-based lookup against crop_reference.json's cover_crops list, ordered by a "
            "KNeighborsClassifier(n_neighbors=5) trained on a synthetic 'similar farm profiles' "
            "dataset (available water, soil organic carbon, is current crop a legume) predicting "
            "whether farms like this one benefit more from a fast N-fixing cover crop."
        ),
        "is_dummy_data": True,
    }
    return ModuleResponse.ok(MODULE_NAME, summary, details, confidence=None)
