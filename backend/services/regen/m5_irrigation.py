"""
MODULE 5 - Water-Use Efficiency / Irrigation Scheduler.

Reads : EnrichedFeatureVector (water_source, crop, sowing_date, weather)
Writes: ModuleResponse(module_name="irrigation_efficiency") with
        details = {next_irrigation_date, water_volume_mm, note,
                   cumulative_water_saved_liters}

MODEL: a small LinearRegression predicting `irrigate_in_days` from
(deficit_mm, crop-coefficient Kc, ET0) - trained once at import on a
synthetic dataset built from the same water-balance physics Part A's
irrigation module already uses (services/modules/irrigation.py), not on
real observed irrigation-timing outcomes (none exist yet). Special case:
`water_source == "rainfed"` skips the model and returns rainfall-dependent
advice instead of a schedule, per the spec.

The REQUIRED "advanced layer" is `cumulative_water_saved_liters`: modelled
water use so far under this deficit-driven approach vs. a naive fixed
weekly-irrigation baseline, using the farm's own rainfall snapshot to
estimate how much of the naive schedule would have been redundant. This is
an approximation (Part A's weather stub only gives a rainfall snapshot, not
a full daily history since sowing) - documented inline.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
from sklearn.linear_model import LinearRegression

from models.schemas import ModuleResponse
from services.modules.common import (
    IRRIGATION_CAPACITY_MM,
    IRRIGATION_EFFICIENCY,
    IRRIGATION_LABELS,
    STAGE_CROP_COEFFICIENT,
    as_value,
    litres_for,
)
from services.regen.feature_resolver import EnrichedFeatureVector

MODULE_NAME = "irrigation_efficiency"
EFFECTIVE_RAINFALL_FRACTION = 0.75


def _train_schedule_model(seed: int = 42) -> LinearRegression:
    """
    Synthetic training set: for a spread of (deficit_mm, Kc, ET0), the
    label is the same "how soon" logic Part A's rule-based irrigation
    module already encodes (deficit relative to weekly demand -> 0/2/4/7+
    days), fit with noise so the regressor generalises smoothly between
    those buckets instead of just memorising them.
    """
    rng = np.random.default_rng(seed)
    n = 600
    deficit = rng.uniform(-60, 120, n)
    kc = rng.uniform(0.3, 1.2, n)
    et0 = rng.uniform(1.5, 9.0, n)
    demand_7d = et0 * kc * 7

    days = np.where(
        deficit <= 0,
        7.0,
        np.where(
            deficit >= demand_7d * 0.75,
            0.0,
            np.where(deficit >= demand_7d * 0.4, 2.0, 4.0),
        ),
    )
    days = days + rng.normal(0, 0.6, n)
    days = np.clip(days, 0, 10)

    X = np.column_stack([deficit, kc, et0])
    model = LinearRegression()
    model.fit(X, days)
    return model


_MODEL = _train_schedule_model()


def run(vector: EnrichedFeatureVector) -> ModuleResponse:
    aggregated = vector.aggregated
    weather = aggregated.weather
    crop = aggregated.crop_reference
    farm = aggregated.farm_input
    source = as_value(farm.irrigation_source)
    source_label = IRRIGATION_LABELS.get(source, source)

    if weather is None:
        return ModuleResponse.error(
            MODULE_NAME,
            summary="Weather data is unavailable, so an irrigation schedule cannot be produced.",
            details={
                "next_irrigation_date": None,
                "water_volume_mm": None,
                "note": "Weather service did not respond.",
                "cumulative_water_saved_liters": 0,
            },
        )

    kc = STAGE_CROP_COEFFICIENT.get(aggregated.crop_stage_hint, 0.85)
    demand_7d_mm = weather.et0_mm_per_day * kc * 7
    recent_effective = weather.rainfall_last_7d_mm * EFFECTIVE_RAINFALL_FRACTION
    forecast_effective = weather.rainfall_forecast_7d_mm * EFFECTIVE_RAINFALL_FRACTION
    deficit_mm = round(demand_7d_mm - recent_effective - forecast_effective, 1)

    # --- cumulative water-saved counter (advanced layer) -------------------
    days_elapsed = max(aggregated.days_since_sowing, 0)
    naive_total_mm = 0.0
    if crop is not None and crop.typical_irrigation_count and crop.typical_irrigation_count > 0:
        per_irrigation_mm = crop.water_requirement_mm / crop.typical_irrigation_count
        naive_irrigations_so_far = days_elapsed // 7
        naive_total_mm = per_irrigation_mm * naive_irrigations_so_far
    rain_rate_mm_per_day = weather.rainfall_last_30d_mm / 30.0
    # Approximation - Part A's weather stub only gives a rainfall snapshot,
    # not a full daily history since sowing, so this projects today's rate
    # backward over the elapsed period.
    cumulative_rain_estimate_mm = rain_rate_mm_per_day * days_elapsed * EFFECTIVE_RAINFALL_FRACTION
    water_saved_mm = max(0.0, min(cumulative_rain_estimate_mm, naive_total_mm))
    cumulative_water_saved_liters = litres_for(water_saved_mm, aggregated.land_size_hectare)
    # 0-100 sub-score for the Regeneration Score Engine: share of the naive
    # fixed-schedule water this deficit-driven approach avoided.
    water_efficiency_score = round(min(100.0, (water_saved_mm / naive_total_mm * 100)) if naive_total_mm > 0 else 50.0, 1)

    # --- special case: rain-fed farms get rainfall advice, not a schedule --
    if source == "rainfed":
        # No pump schedule to save against - score how well rainfall alone
        # covers demand instead.
        water_efficiency_score = round(
            min(100.0, (recent_effective + forecast_effective) / demand_7d_mm * 100) if demand_7d_mm > 0 else 100.0, 1
        )
        if deficit_mm > 0:
            note = (
                f"Rain-fed field - no pump to schedule. Expected rain over the next 7 days covers "
                f"{recent_effective + forecast_effective:.0f} mm of the {demand_7d_mm:.0f} mm the crop needs; "
                f"mulch and conserve moisture to cover the {deficit_mm:.0f} mm gap."
            )
        else:
            note = (
                f"Rain-fed field - rainfall ({recent_effective + forecast_effective:.0f} mm expected) "
                f"already covers this week's {demand_7d_mm:.0f} mm need. No action needed."
            )
        details = {
            "irrigation_source": source,
            "irrigation_source_label": source_label,
            "next_irrigation_date": None,
            "water_volume_mm": None,
            "note": note,
            "water_balance": {
                "demand_next_7d_mm": round(demand_7d_mm, 1),
                "rain_last_7d_mm": weather.rainfall_last_7d_mm,
                "rain_forecast_7d_mm": weather.rainfall_forecast_7d_mm,
                "deficit_mm": deficit_mm,
            },
            "cumulative_water_saved_liters": cumulative_water_saved_liters,
            "water_efficiency_score": water_efficiency_score,
            "is_dummy_data": True,
        }
        return ModuleResponse.ok(MODULE_NAME, note[:120], details, confidence=None)

    # --- regression-predicted schedule --------------------------------------
    predicted_days = float(_MODEL.predict([[deficit_mm, kc, weather.et0_mm_per_day]])[0])
    predicted_days = max(0, round(predicted_days))
    next_date = date.today() + timedelta(days=predicted_days)

    efficiency = IRRIGATION_EFFICIENCY.get(source, 0.6)
    gross_depth_mm = round(max(deficit_mm, 0.0) / efficiency, 1) if deficit_mm > 0 else 0.0

    if deficit_mm <= 0:
        note = f"No irrigation needed this week - rain covers the {demand_7d_mm:.0f} mm demand."
    elif predicted_days == 0:
        note = f"Irrigate today - about {gross_depth_mm:.0f} mm."
    else:
        note = f"Next irrigation in about {predicted_days} day(s) - roughly {gross_depth_mm:.0f} mm."

    details = {
        "irrigation_source": source,
        "irrigation_source_label": source_label,
        "next_irrigation_date": next_date.isoformat(),
        "water_volume_mm": gross_depth_mm,
        "water_volume_litres": litres_for(gross_depth_mm, aggregated.land_size_hectare),
        "note": note,
        "water_balance": {
            "demand_next_7d_mm": round(demand_7d_mm, 1),
            "et0_mm_per_day": weather.et0_mm_per_day,
            "rain_last_7d_mm": weather.rainfall_last_7d_mm,
            "rain_forecast_7d_mm": weather.rainfall_forecast_7d_mm,
            "deficit_mm": deficit_mm,
        },
        "cumulative_water_saved_liters": cumulative_water_saved_liters,
        "water_efficiency_score": water_efficiency_score,
        "model": "LinearRegression(deficit_mm, Kc, ET0) -> irrigate_in_days, trained on a synthetic water-balance dataset",
        "is_dummy_data": True,
    }

    if crop is None:
        return ModuleResponse.partial(MODULE_NAME, f"{note} (Crop not in guide - general estimate.)", details, confidence=None)
    return ModuleResponse.ok(MODULE_NAME, note, details, confidence=None)
