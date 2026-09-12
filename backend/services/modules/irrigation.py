"""
MODULE 2/4 - Irrigation advice.

Reads : AggregatedData.weather, .crop_reference, .farm_input, .crop_stage_hint
Writes: ModuleResponse(module_name="irrigation_advice")

=========================================================================
 TODO(ML): REPLACE THE BODY OF `run()` WITH A REAL MODEL
 -----------------------------------------------------------------------
 Today: a simple ET0 x Kc water-balance against recent + forecast rainfall.
 Tomorrow: a soil-moisture model driven by satellite (SMAP / Sentinel-1)
 or in-field sensors, predicting the next irrigation date directly and
 reporting a real `confidence`.

 Contract to preserve:
   * signature      run(aggregated: AggregatedData) -> ModuleResponse
   * module_name    "irrigation_advice"
   * details keys   action, irrigate_in_days, depth_mm, water_litres,
                    water_balance, next_critical_stage, farmer_actions[]
=========================================================================
"""

from __future__ import annotations

from models.schemas import AggregatedData, ModuleResponse
from services.modules.common import (
    IRRIGATION_CAPACITY_MM,
    IRRIGATION_EFFICIENCY,
    IRRIGATION_LABELS,
    STAGE_CROP_COEFFICIENT,
    as_value,
    litres_for,
)

MODULE_NAME = "irrigation_advice"

# Fraction of rainfall that actually reaches the root zone (rest runs off).
EFFECTIVE_RAINFALL_FRACTION = 0.75


def run(aggregated: AggregatedData) -> ModuleResponse:
    weather = aggregated.weather
    crop = aggregated.crop_reference
    farm = aggregated.farm_input
    source = as_value(farm.irrigation_source)
    source_label = IRRIGATION_LABELS.get(source, source)

    if weather is None:
        return ModuleResponse.error(
            MODULE_NAME,
            summary="Weather data is unavailable right now, so irrigation advice cannot be given.",
            details={
                "action": "unknown",
                "irrigate_in_days": None,
                "depth_mm": None,
                "water_litres": None,
                "water_balance": None,
                "next_critical_stage": None,
                "farmer_actions": ["Check back shortly - weather service did not respond."],
            },
        )

    # --- 1. weekly crop water demand --------------------------------------
    kc = STAGE_CROP_COEFFICIENT.get(aggregated.crop_stage_hint, 0.85)
    demand_7d_mm = round(weather.et0_mm_per_day * kc * 7, 1)

    # Cross-check against the crop's own seasonal figure when we have it.
    seasonal_note = None
    if crop is not None and crop.growth_duration_days > 0:
        season_avg_7d = crop.water_requirement_mm / crop.growth_duration_days * 7
        seasonal_note = (
            f"{crop.crop_name} needs about {crop.water_requirement_mm:.0f} mm over "
            f"{crop.growth_duration_days} days (~{season_avg_7d:.0f} mm per week on average)."
        )

    # --- 2. what the sky is providing -------------------------------------
    recent_effective = round(weather.rainfall_last_7d_mm * EFFECTIVE_RAINFALL_FRACTION, 1)
    forecast_effective = round(weather.rainfall_forecast_7d_mm * EFFECTIVE_RAINFALL_FRACTION, 1)
    deficit_mm = round(demand_7d_mm - recent_effective - forecast_effective, 1)

    efficiency = IRRIGATION_EFFICIENCY.get(source, 0.6)
    gross_depth_mm = round(max(deficit_mm, 0.0) / efficiency, 1) if deficit_mm > 0 else 0.0

    # --- 3. turn the number into an instruction ---------------------------
    if aggregated.days_since_sowing < 0:
        action = "pre_sowing"
        irrigate_in_days = None
        summary = (
            f"Crop not sown yet. Make sure the field has enough moisture "
            f"({'rain is expected' if forecast_effective > 15 else 'consider a pre-sowing irrigation'})."
        )
    elif aggregated.crop_stage_hint == "past_harvest":
        action = "stop"
        irrigate_in_days = None
        summary = "Crop has passed its harvest window. Stop irrigating and plan the next season."
    elif source == "rainfed":
        action = "conserve" if deficit_mm > 0 else "none"
        irrigate_in_days = None
        if deficit_mm > 0:
            summary = (
                f"Rain-fed field is short by about {deficit_mm:.0f} mm this week. "
                "Focus on conserving moisture."
            )
        else:
            summary = "Rainfall is enough for your crop this week. No action needed."
    elif deficit_mm <= 0:
        action = "none"
        irrigate_in_days = None
        summary = (
            f"No irrigation needed. Recent and expected rain covers "
            f"{recent_effective + forecast_effective:.0f} mm against a need of {demand_7d_mm:.0f} mm."
        )
    elif forecast_effective >= demand_7d_mm * 0.6:
        action = "wait"
        irrigate_in_days = 4
        summary = f"Rain is expected soon. Wait about 4 days before irrigating."
    elif deficit_mm >= demand_7d_mm * 0.75:
        action = "irrigate_now"
        irrigate_in_days = 0
        summary = (
            f"Irrigate now - about {gross_depth_mm:.0f} mm "
            f"({litres_for(gross_depth_mm, aggregated.land_size_hectare):,} litres for your field)."
        )
    else:
        action = "irrigate_soon"
        irrigate_in_days = 2
        summary = (
            f"Irrigate in about 2 days - roughly {gross_depth_mm:.0f} mm "
            f"({litres_for(gross_depth_mm, aggregated.land_size_hectare):,} litres for your field)."
        )

    # --- 4. next critical stage -------------------------------------------
    next_stage = None
    if crop is not None and crop.critical_irrigation_stages:
        upcoming = [
            stage
            for stage in crop.critical_irrigation_stages
            if stage.days_after_sowing >= aggregated.days_since_sowing
        ]
        if upcoming:
            stage = min(upcoming, key=lambda s: s.days_after_sowing)
            next_stage = {
                "stage": stage.stage,
                "days_after_sowing": stage.days_after_sowing,
                "days_from_today": stage.days_after_sowing - aggregated.days_since_sowing,
                "note": stage.note,
            }

    # --- 5. actions --------------------------------------------------------
    actions: list[str] = []
    if source == "rainfed" and deficit_mm > 0:
        actions.append("Mulch with crop residue to hold soil moisture.")
        actions.append("Weed now - weeds compete for the little water you have.")
    if source in ("canal", "tank_pond") and gross_depth_mm > 0:
        actions.append("Canal/tank water loses ~45% to seepage. Irrigate early morning or evening.")
    if source in ("borewell", "tubewell") and gross_depth_mm > 0:
        actions.append("Consider drip or sprinkler - it would cut this week's pumping by about a third.")
    if source == "drip_sprinkler":
        actions.append("Run drip in 2 shorter cycles rather than 1 long one for better uptake.")
    if next_stage and next_stage["days_from_today"] <= 7:
        actions.append(
            f"'{next_stage['stage']}' stage starts in {next_stage['days_from_today']} days - "
            "do not miss that irrigation."
        )
    if not actions:
        actions.append("Keep checking soil moisture at 5-6 inch depth before each irrigation.")

    details = {
        "action": action,
        "irrigate_in_days": irrigate_in_days,
        "depth_mm": gross_depth_mm,
        "water_litres": litres_for(gross_depth_mm, aggregated.land_size_hectare),
        "irrigation_source": source,
        "irrigation_source_label": source_label,
        "source_capacity_mm_per_season": IRRIGATION_CAPACITY_MM.get(source),
        "application_efficiency": efficiency,
        "crop_stage": aggregated.crop_stage_hint,
        "crop_coefficient_kc": kc,
        "water_balance": {
            "demand_next_7d_mm": demand_7d_mm,
            "et0_mm_per_day": weather.et0_mm_per_day,
            "rain_last_7d_mm": weather.rainfall_last_7d_mm,
            "rain_forecast_7d_mm": weather.rainfall_forecast_7d_mm,
            "effective_rain_mm": round(recent_effective + forecast_effective, 1),
            "deficit_mm": deficit_mm,
        },
        "seasonal_note": seasonal_note,
        "next_critical_stage": next_stage,
        "forecast": [day.model_dump() for day in weather.forecast[:5]],
        "weather_source": weather.source,
        "farmer_actions": actions,
        "is_dummy_data": True,  # TODO(ML): flip to False when a real model lands
    }

    # Without the crop table we are guessing at Kc and season length.
    if crop is None:
        return ModuleResponse.partial(
            MODULE_NAME,
            summary=f"{summary} (Crop not in our guide, so this is a general estimate.)",
            details=details,
            confidence=None,
        )
    return ModuleResponse.ok(MODULE_NAME, summary, details, confidence=None)
