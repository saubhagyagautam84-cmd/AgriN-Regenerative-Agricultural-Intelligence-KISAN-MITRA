"""
MODULE 4/4 - Crop rotation planner.

Reads : AggregatedData.crop_reference, .soil, .farm_input
Writes: ModuleResponse(module_name="rotation_suggestion")

=========================================================================
 TODO(ML): REPLACE THE BODY OF `run()` WITH A REAL PLANNER
 -----------------------------------------------------------------------
 Today: a greedy walk over `rotation_compatible_with` / `rotation_avoid`
 from data/crop_reference.json, one crop per upcoming season.
 Tomorrow: a multi-season optimiser over soil nutrient balance, pest
 pressure, labour and market price, with a real `confidence`.

 Contract to preserve:
   * signature      run(aggregated: AggregatedData) -> ModuleResponse
   * module_name    "rotation_suggestion"
   * details keys   current_crop, plan[], avoid[], farmer_actions[]
     where each plan entry is
       {sequence, season, season_label, window, crop_name, local_name,
        is_legume, reason}
=========================================================================
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from models.schemas import AggregatedData, CropReference, ModuleResponse
from services import data_loader
from services.modules.common import (
    SEASON_LABELS,
    as_value,
    next_season,
    rate_nutrient,
)

MODULE_NAME = "rotation_suggestion"

PLAN_LENGTH = 3  # how many seasons ahead to sketch

SEASON_ORDER = ["kharif", "rabi", "zaid"]
SEASON_WINDOWS = {
    "kharif": "June - October (with the monsoon)",
    "rabi": "November - March (winter)",
    "zaid": "March - May (summer)",
}


def _following_season(season: str) -> str:
    return SEASON_ORDER[(SEASON_ORDER.index(season) + 1) % len(SEASON_ORDER)]


def _pick_for_season(
    season: str,
    candidates: list[CropReference],
    preferred_names: list[str],
    avoid_names: set[str],
    already_used: set[str],
) -> Optional[CropReference]:
    """Best crop for one season: prefer the rotation list, never repeat, never use an avoided crop."""
    in_season = [
        crop
        for crop in candidates
        if as_value(crop.season) == season
        and crop.crop_name not in already_used
        and crop.crop_name not in avoid_names
    ]
    if not in_season:
        return None

    preferred = [crop for crop in in_season if crop.crop_name in preferred_names]
    pool = preferred or in_season

    # Nudge towards legumes - they are what makes a rotation worth doing.
    pool.sort(key=lambda crop: (not crop.is_legume, crop.crop_name))
    return pool[0]


def run(aggregated: AggregatedData) -> ModuleResponse:
    farm = aggregated.farm_input
    current = aggregated.crop_reference
    soil = aggregated.soil

    _index, all_crops, _report = data_loader.load_crop_reference()

    if current is None or not all_crops:
        return ModuleResponse.partial(
            MODULE_NAME,
            summary=(
                f"'{farm.crop_name}' is not in our crop guide yet, so we cannot plan a rotation for it."
            ),
            details={
                "current_crop": farm.crop_name,
                "plan": [],
                "avoid": [],
                "farmer_actions": [
                    "As a general rule, follow a cereal with a pulse, and never grow the same crop twice in a row.",
                ],
                "is_dummy_data": True,
            },
            confidence=None,
        )

    avoid_names = set(current.rotation_avoid)
    preferred_names = list(current.rotation_compatible_with)

    season_enum, first_window = next_season()
    season = season_enum.value

    plan: list[dict] = []
    used: set[str] = {current.crop_name}
    year = date.today().year

    for step in range(PLAN_LENGTH):
        pick = _pick_for_season(season, all_crops, preferred_names, avoid_names, used)
        if pick is None:
            season = _following_season(season)
            continue

        if step == 0:
            reason = f"Recommended in ICAR guidance to follow {current.crop_name}"
        elif pick.is_legume:
            reason = "Legume - restores nitrogen and breaks the pest cycle"
        else:
            reason = f"Different crop family from {plan[-1]['crop_name']} - keeps soil-borne pests down"

        plan.append(
            {
                "sequence": step + 1,
                "season": season,
                "season_label": SEASON_LABELS.get(season, season),
                "window": f"{SEASON_WINDOWS.get(season, season)}, {year + (1 if season == 'rabi' and step > 0 else 0)}",
                "crop_name": pick.crop_name,
                "local_name": pick.local_names.get("hi"),
                "is_legume": pick.is_legume,
                "duration_days": pick.growth_duration_days,
                "water_requirement_mm": pick.water_requirement_mm,
                "reason": reason,
            }
        )
        used.add(pick.crop_name)
        # After the first pick, later picks are judged against the previous one.
        preferred_names = list(pick.rotation_compatible_with)
        avoid_names = set(pick.rotation_avoid)
        season = _following_season(season)
        if season == "kharif":
            year += 1

    if not plan:
        return ModuleResponse.partial(
            MODULE_NAME,
            summary=f"No suitable rotation found after {current.crop_name} in our current crop guide.",
            details={
                "current_crop": current.crop_name,
                "plan": [],
                "avoid": sorted(set(current.rotation_avoid)),
                "farmer_actions": ["Add more crops to data/crop_reference.json to improve this plan."],
                "is_dummy_data": True,
            },
            confidence=None,
        )

    first = plan[0]
    local = f" ({first['local_name']})" if first["local_name"] else ""
    summary = f"After {current.crop_name}, sow {first['crop_name']}{local} in {first['season_label']}."

    actions: list[str] = []
    if current.crop_name in current.rotation_avoid:
        actions.append(
            f"Do not sow {current.crop_name} again next season - repeating it builds up pests and drains the soil."
        )
    if not any(entry["is_legume"] for entry in plan):
        actions.append("Try to fit a pulse (chana, soybean or groundnut) into the cycle to restore nitrogen.")
    else:
        legume = next(entry["crop_name"] for entry in plan if entry["is_legume"])
        actions.append(f"{legume} in this plan will add nitrogen back - reduce urea for the crop after it.")
    if soil is not None and rate_nutrient("organic_carbon_pct", soil.organic_carbon_pct) == "low":
        actions.append("Leave crop residue in the field between seasons - your organic carbon is low.")
    actions.append(f"Avoid after {current.crop_name}: {', '.join(current.rotation_avoid) or 'nothing specific'}.")

    details = {
        "current_crop": current.crop_name,
        "current_crop_local_name": current.local_names.get("hi"),
        "first_window": first_window,
        "plan": plan,
        "avoid": sorted(set(current.rotation_avoid)),
        "compatible_with": sorted(set(current.rotation_compatible_with)),
        "farmer_actions": actions,
        "planning_method": "greedy walk over the ICAR rotation lists in crop_reference.json",
        "is_dummy_data": True,  # TODO(ML): flip to False when a real planner lands
    }

    return ModuleResponse.ok(MODULE_NAME, summary, details, confidence=None)
