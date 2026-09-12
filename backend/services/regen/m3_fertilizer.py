"""
MODULE 3 - Fertilizer / Pesticide Reducer. Highest priority module.

Reads : EnrichedFeatureVector (crop's N/P/K/water needs, resolved soil NPK,
        growth stage from sowing_date, weather ET0)
Writes: ModuleResponse(module_name="fertilizer") with
        details = {recommended_npk, current_estimated_usage,
                   reduction_percent, explanation}

MODEL: a real scikit-learn RandomForestRegressor (multi-output: N, P, K in
one forest), trained ONCE at import time on a SYNTHETIC dataset built from
crop_reference.json's ICAR-sourced seasonal N/P/K totals. No real
farm-level observational dataset exists yet (this is the honest limitation
stated in the project brief), so training labels are generated from a
physically-grounded rule: each crop's seasonal NPK requirement is split
across its growth-stage curve (reusing Part A's STAGE_CROP_COEFFICIENT Kc
curve from services/modules/common.py, applied to nutrient demand as well
as water demand - a simplifying assumption, not a per-crop published
stage-split table) and adjusted by the soil test's low/medium/high rating
(same DOSE_FACTOR reused from services/modules/soil_status.py). This keeps
the model swap-in-ready: replace `_build_synthetic_training_set()` with a
loader over real agronomic trial data and nothing downstream changes.

`current_estimated_usage` (the "typical farmer usage" baseline) is modelled
on the commonly-cited pattern of imbalanced fertiliser use in India - urea
(N) over-applied because it is cheap/subsidised, potash (K) under-applied
because MOP is not (widely discussed in Fertiliser Association of India /
agricultural-economics commentary, e.g. actual national N:P:K use ratio
running well above the ICAR-recommended ~4:2:1 balance). The multipliers
below are illustrative round numbers, not a specific cited study - calibrate
with local extension data before real deployment.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from models.schemas import ModuleResponse
from services.modules.common import STAGE_CROP_COEFFICIENT, rate_nutrient
from services.modules.soil_status import DOSE_FACTOR
from services.regen.feature_resolver import EnrichedFeatureVector

MODULE_NAME = "fertilizer"

FEATURE_NAMES = [
    "crop_total_N_kg_per_ha",
    "crop_total_P_kg_per_ha",
    "crop_total_K_kg_per_ha",
    "growth_stage_fraction",
    "soil_N_score",
    "soil_P_score",
    "soil_K_score",
    "soil_pH_deviation_from_ideal",
    "et0_mm_per_day",
]

# Same 0-100 scale M2 uses for SHC ratings.
RATING_SCORE = {"low": 40.0, "medium": 75.0, "high": 100.0}

# Sum of the 5 "in-season" Kc buckets - used to turn a bucket's coefficient
# into "fraction of the season's total nutrient demand happening now".
_PRODUCTIVE_STAGES = ["establishment", "vegetative", "flowering", "grain_filling", "maturity"]
_KC_SUM = sum(STAGE_CROP_COEFFICIENT[s] for s in _PRODUCTIVE_STAGES)


def _stage_fraction(stage_hint: str) -> float:
    if stage_hint in ("not_sown_yet",):
        return STAGE_CROP_COEFFICIENT["establishment"] / _KC_SUM  # pre-plant/basal dose
    if stage_hint == "past_harvest":
        return 0.0
    kc = STAGE_CROP_COEFFICIENT.get(stage_hint, STAGE_CROP_COEFFICIENT["unknown"])
    return kc / _KC_SUM


# "Typical farmer usage" imbalance multipliers - see module docstring.
FARMER_USAGE_FACTOR = {"N": 1.30, "P": 0.85, "K": 0.55}


def _build_synthetic_training_set(
    crops: list, samples_per_crop_stage: int = 12, seed: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    X: list[list[float]] = []
    y: list[list[float]] = []

    ratings = ["low", "medium", "high"]
    for crop in crops:
        for stage in _PRODUCTIVE_STAGES:
            stage_frac = STAGE_CROP_COEFFICIENT[stage] / _KC_SUM
            for _ in range(samples_per_crop_stage):
                n_rating = ratings[rng.integers(0, 3)]
                p_rating = ratings[rng.integers(0, 3)]
                k_rating = ratings[rng.integers(0, 3)]
                ph_deviation = float(rng.uniform(0, 2.0))
                et0 = float(rng.uniform(1.5, 9.0))

                n_target = crop.n_requirement_kg_per_ha * stage_frac * DOSE_FACTOR[n_rating]
                p_target = crop.p_requirement_kg_per_ha * stage_frac * DOSE_FACTOR[p_rating]
                k_target = crop.k_requirement_kg_per_ha * stage_frac * DOSE_FACTOR[k_rating]
                # Small ET0-driven noise: faster growth under warmer/higher-ET0
                # conditions pulls slightly more N.
                n_target *= 1.0 + 0.01 * (et0 - 5.0)
                noise = rng.normal(0, 0.03, size=3)
                n_target = max(0.0, n_target * (1 + noise[0]))
                p_target = max(0.0, p_target * (1 + noise[1]))
                k_target = max(0.0, k_target * (1 + noise[2]))

                X.append(
                    [
                        crop.n_requirement_kg_per_ha,
                        crop.p_requirement_kg_per_ha,
                        crop.k_requirement_kg_per_ha,
                        stage_frac,
                        RATING_SCORE[n_rating],
                        RATING_SCORE[p_rating],
                        RATING_SCORE[k_rating],
                        ph_deviation,
                        et0,
                    ]
                )
                y.append([n_target, p_target, k_target])

    return np.array(X), np.array(y)


def _train_model() -> RandomForestRegressor:
    from services import data_loader

    _index, all_crops, _report = data_loader.load_crop_reference()
    if not all_crops:
        return None  # type: ignore[return-value]
    X, y = _build_synthetic_training_set(all_crops)
    model = RandomForestRegressor(n_estimators=80, max_depth=8, random_state=42)
    model.fit(X, y)
    return model


_MODEL: RandomForestRegressor | None = None


def _get_model() -> RandomForestRegressor | None:
    global _MODEL
    if _MODEL is None:
        _MODEL = _train_model()
    return _MODEL


def run(vector: EnrichedFeatureVector) -> ModuleResponse:
    aggregated = vector.aggregated
    crop = aggregated.crop_reference
    weather = aggregated.weather

    if crop is None:
        return ModuleResponse.partial(
            MODULE_NAME,
            summary=f"'{aggregated.farm_input.crop_name}' is not in our crop guide yet, so no fertiliser model can run.",
            details={
                "recommended_npk": None,
                "current_estimated_usage": None,
                "reduction_percent": None,
                "explanation": [],
                "is_dummy_data": True,
            },
            confidence=None,
        )

    model = _get_model()
    if model is None:
        return ModuleResponse.error(
            MODULE_NAME,
            summary="Fertiliser model could not be trained (crop reference table failed to load).",
            details={"recommended_npk": None, "current_estimated_usage": None, "reduction_percent": None, "explanation": []},
        )

    stage_frac = _stage_fraction(aggregated.crop_stage_hint)
    soil = vector.soil
    n_score = RATING_SCORE.get(rate_nutrient("n_kg_per_ha", soil.n_kg_per_ha.value) or "medium", 75.0)
    p_score = RATING_SCORE.get(rate_nutrient("p_kg_per_ha", soil.p_kg_per_ha.value) or "medium", 75.0)
    k_score = RATING_SCORE.get(rate_nutrient("k_kg_per_ha", soil.k_kg_per_ha.value) or "medium", 75.0)
    ph_deviation = 0.0
    if soil.ph.value is not None:
        lo, hi = crop.ideal_soil_ph.min, crop.ideal_soil_ph.max
        if soil.ph.value < lo:
            ph_deviation = lo - soil.ph.value
        elif soil.ph.value > hi:
            ph_deviation = soil.ph.value - hi
    et0 = weather.et0_mm_per_day if weather is not None else 4.5  # mild fallback, mid-range

    features = np.array(
        [
            [
                crop.n_requirement_kg_per_ha,
                crop.p_requirement_kg_per_ha,
                crop.k_requirement_kg_per_ha,
                stage_frac,
                n_score,
                p_score,
                k_score,
                ph_deviation,
                et0,
            ]
        ]
    )
    n_pred, p_pred, k_pred = model.predict(features)[0]
    area = aggregated.land_size_hectare

    recommended = {
        "N_kg_per_ha": round(float(n_pred), 1),
        "P_kg_per_ha": round(float(p_pred), 1),
        "K_kg_per_ha": round(float(k_pred), 1),
        "N_kg_for_field": round(float(n_pred) * area, 1),
        "P_kg_for_field": round(float(p_pred) * area, 1),
        "K_kg_for_field": round(float(k_pred) * area, 1),
    }

    current_usage = {
        "N_kg_per_ha": round(float(n_pred) * FARMER_USAGE_FACTOR["N"], 1),
        "P_kg_per_ha": round(float(p_pred) * FARMER_USAGE_FACTOR["P"], 1),
        "K_kg_per_ha": round(float(k_pred) * FARMER_USAGE_FACTOR["K"], 1),
    }

    total_recommended = n_pred + p_pred + k_pred
    total_current = sum(current_usage.values())
    reduction_percent = (
        round((total_current - total_recommended) / total_current * 100, 1) if total_current > 0 else 0.0
    )

    # --- explainability: feature_importances_ from the trained forest -----
    importances = model.feature_importances_
    ranked = sorted(zip(FEATURE_NAMES, importances), key=lambda pair: pair[1], reverse=True)
    top_features = ranked[:3]
    top_sum = sum(imp for _, imp in top_features) or 1.0
    explanation = [
        {
            "feature": name,
            "contribution_pct": round(float(imp) / top_sum * 100, 1),
        }
        for name, imp in top_features
    ]

    # 0-100 sub-score for the Regeneration Score Engine: how much of the
    # farmer's typical over-application this recommendation removes, capped
    # at a 50%-reduction ceiling (beyond that, more "reduction" just means
    # the baseline assumption was extreme, not that the advice is better).
    reduction_efficiency_score = round(max(0.0, min(reduction_percent, 50.0)) / 50.0 * 100, 1)

    nutrient_notes = []
    if current_usage["K_kg_per_ha"] < recommended["K_kg_per_ha"]:
        nutrient_notes.append("Potash (K) is typically under-applied - you may need MORE K, not less.")
    if current_usage["N_kg_per_ha"] > recommended["N_kg_per_ha"]:
        nutrient_notes.append(f"Nitrogen (urea) can likely be cut by about {reduction_percent:.0f}% at this stage without hurting yield.")

    summary = (
        f"At the {aggregated.crop_stage_hint.replace('_', ' ')} stage, {crop.crop_name} needs about "
        f"{recommended['N_kg_per_ha']:.0f}-{recommended['P_kg_per_ha']:.0f}-{recommended['K_kg_per_ha']:.0f} "
        f"kg/ha N-P-K - roughly {max(reduction_percent, 0):.0f}% less total fertiliser than typical usage."
    )

    details = {
        "current_crop": crop.crop_name,
        "growth_stage": aggregated.crop_stage_hint,
        "recommended_npk": recommended,
        "current_estimated_usage": current_usage,
        "reduction_percent": reduction_percent,
        "reduction_efficiency_score": reduction_efficiency_score,
        "explanation": explanation,
        "farmer_actions": nutrient_notes or ["Follow the recommended split dose above for this growth stage."],
        "model": "RandomForestRegressor (multi-output N/P/K), trained on a synthetic ICAR-derived dataset - see module docstring",
        "is_dummy_data": True,
    }
    return ModuleResponse.ok(MODULE_NAME, summary, details, confidence=None)
