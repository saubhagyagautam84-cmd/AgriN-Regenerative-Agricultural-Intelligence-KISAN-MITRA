"""
MODULE 3/4 - Crop recommendation.

Reads : AggregatedData.soil, .weather, .crop_reference, .farm_input
        + the full crop table (via data_loader, which is cached)
Writes: ModuleResponse(module_name="crop_recommendation")

=========================================================================
 TODO(ML): REPLACE THE BODY OF `run()` WITH A REAL MODEL
 -----------------------------------------------------------------------
 Today: a transparent additive score over four rules (season fit, pH fit,
 water fit, rotation fit). `confidence` is HARD-CODED - see DUMMY_CONFIDENCE
 below. It is a placeholder so the UI has something to render.

 Tomorrow: a classifier/ranker trained on yield + price outcomes. It should
 emit a genuine probability into `confidence` and delete DUMMY_CONFIDENCE.

 Contract to preserve:
   * signature      run(aggregated: AggregatedData) -> ModuleResponse
   * module_name    "crop_recommendation"
   * details keys   target_season, recommendations[], considered_count,
                    farmer_actions[]
     where each recommendation is
       {crop_name, local_name, score, season, water_requirement_mm,
        duration_days, reasons[], warnings[]}
=========================================================================
"""

from __future__ import annotations

from models.schemas import AggregatedData, ModuleResponse
from services import data_loader
from services.modules.common import (
    IRRIGATION_CAPACITY_MM,
    SEASON_LABELS,
    SEASON_RAINFALL_MM,
    as_value,
    next_season,
    rate_nutrient,
)

MODULE_NAME = "crop_recommendation"

# !!! PLACEHOLDER !!! Rule-based scoring has no meaningful probability, so we
# report a deliberately modest fixed number. Delete this when a model lands.
DUMMY_CONFIDENCE = 0.55

MAX_RECOMMENDATIONS = 3


def run(aggregated: AggregatedData) -> ModuleResponse:
    farm = aggregated.farm_input
    soil = aggregated.soil
    current_crop = aggregated.crop_reference

    _index, all_crops, _report = data_loader.load_crop_reference()
    if not all_crops:
        return ModuleResponse.error(
            MODULE_NAME,
            summary="Crop guide could not be loaded, so no suggestions are available.",
            details={
                "target_season": None,
                "recommendations": [],
                "considered_count": 0,
                "farmer_actions": ["Contact support - the crop reference file is missing or invalid."],
            },
        )

    target_season, season_window = next_season()
    target = target_season.value
    source = as_value(farm.irrigation_source)

    # How much water the farm can actually put on a crop next season.
    available_water_mm = SEASON_RAINFALL_MM.get(target, 200.0) + IRRIGATION_CAPACITY_MM.get(source, 400.0)

    soil_n_rating = rate_nutrient("n_kg_per_ha", soil.n_kg_per_ha) if soil else None
    current_name = current_crop.crop_name if current_crop else farm.crop_name

    scored: list[dict] = []
    for candidate in all_crops:
        # Do not recommend the crop already in the ground.
        if current_crop is not None and candidate.crop_name == current_crop.crop_name:
            continue

        score = 0.0
        reasons: list[str] = []
        warnings: list[str] = []
        candidate_season = as_value(candidate.season)

        # --- rule 1: does it belong to the coming season? ------------------
        if candidate_season == target:
            score += 30
            reasons.append(f"Fits the coming {SEASON_LABELS.get(target, target)} season")
        elif candidate_season == "perennial":
            score += 12
            reasons.append("Can be planted year-round")
        else:
            continue  # wrong season entirely - not worth showing

        # --- rule 2: soil pH -----------------------------------------------
        if soil is not None and soil.ph is not None:
            low, high = candidate.ideal_soil_ph.min, candidate.ideal_soil_ph.max
            if low <= soil.ph <= high:
                score += 25
                reasons.append(f"Your soil pH {soil.ph} suits this crop")
            elif low - 0.5 <= soil.ph <= high + 0.5:
                score += 12
                warnings.append(f"Soil pH {soil.ph} is just outside the ideal {low}-{high}")
            else:
                warnings.append(f"Soil pH {soil.ph} is unsuitable (ideal {low}-{high})")
        else:
            score += 12  # unknown pH - stay neutral rather than punish

        # --- rule 3: can the farm supply the water? ------------------------
        need = candidate.water_requirement_mm
        if available_water_mm >= need:
            score += 25
            reasons.append("Your water source can meet this crop's needs")
        elif available_water_mm >= need * 0.75:
            score += 12
            warnings.append(
                f"Needs about {need:.0f} mm; you can supply roughly {available_water_mm:.0f} mm"
            )
        else:
            warnings.append(
                f"Too thirsty for your water source (needs {need:.0f} mm, "
                f"you have about {available_water_mm:.0f} mm)"
            )

        # --- rule 4: rotation fit against the current crop -----------------
        if current_crop is not None:
            if candidate.crop_name in current_crop.rotation_compatible_with:
                score += 20
                reasons.append(f"Recommended rotation after {current_crop.crop_name}")
            elif candidate.crop_name in current_crop.rotation_avoid:
                score -= 25
                warnings.append(f"Not advised straight after {current_crop.crop_name}")

        # --- rule 5: legume bonus on nitrogen-poor soil --------------------
        if candidate.is_legume and soil_n_rating == "low":
            score += 10
            reasons.append("Fixes nitrogen - helps your nitrogen-poor soil")

        scored.append(
            {
                "crop_name": candidate.crop_name,
                "local_name": candidate.local_names.get("hi"),
                "score": int(max(0, min(100, round(score)))),
                "season": candidate_season,
                "season_label": SEASON_LABELS.get(candidate_season, candidate_season),
                "water_requirement_mm": candidate.water_requirement_mm,
                "duration_days": candidate.growth_duration_days,
                "is_legume": candidate.is_legume,
                "reasons": reasons,
                "warnings": warnings,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    top = scored[:MAX_RECOMMENDATIONS]

    if not top:
        return ModuleResponse.partial(
            MODULE_NAME,
            summary=f"No {SEASON_LABELS.get(target, target)} crop in our guide matches your conditions yet.",
            details={
                "target_season": target,
                "season_window": season_window,
                "recommendations": [],
                "considered_count": len(all_crops),
                "farmer_actions": ["Talk to your local agriculture officer for options in your area."],
                "is_dummy_data": True,
            },
            confidence=DUMMY_CONFIDENCE,
        )

    best = top[0]
    local = f" ({best['local_name']})" if best["local_name"] else ""
    summary = (
        f"For the coming {SEASON_LABELS.get(target, target)} season, "
        f"{best['crop_name']}{local} suits your land best."
    )

    actions = [
        f"Book certified {best['crop_name']} seed early - {season_window} sowing.",
        f"Plan for about {best['water_requirement_mm']:.0f} mm of water over "
        f"{best['duration_days']} days.",
    ]
    if best["warnings"]:
        actions.append(f"Watch out: {best['warnings'][0]}.")

    details = {
        "target_season": target,
        "season_window": season_window,
        "after_crop": current_name,
        "available_water_mm": round(available_water_mm),
        "recommendations": top,
        "considered_count": len(all_crops),
        "farmer_actions": actions,
        "scoring_method": "rule-based additive score (season 30 / pH 25 / water 25 / rotation 20)",
        "is_dummy_data": True,  # TODO(ML): flip to False when a real model lands
    }

    # No soil card means two of the four rules ran blind - say so honestly.
    if soil is None or current_crop is None:
        return ModuleResponse.partial(MODULE_NAME, summary, details, confidence=DUMMY_CONFIDENCE)
    return ModuleResponse.ok(MODULE_NAME, summary, details, confidence=DUMMY_CONFIDENCE)
