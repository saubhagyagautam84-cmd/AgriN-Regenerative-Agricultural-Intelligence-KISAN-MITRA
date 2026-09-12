"""
STEP 3 - the backbone.

`aggregate_farm_data()` is the single place where the farmer's form input is
joined with every auto-fetched source. Every downstream module (today: rule
stubs; tomorrow: ML models) receives the resulting `AggregatedData` and
returns a `ModuleResponse`. Modules never re-read files and never re-fetch
weather - if a module needs something new, add it here once.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from models.schemas import (
    AggregatedData,
    CropReference,
    FarmInput,
    ModuleResponse,
    SoilData,
)
from services import data_loader, weather as weather_service

MODULE_NAME = "aggregator"


def _crop_stage_hint(days_since_sowing: int, crop: Optional[CropReference]) -> str:
    """Coarse phenology bucket. ML modules can ignore it; the UI uses it."""
    if days_since_sowing < 0:
        return "not_sown_yet"

    duration = crop.growth_duration_days if crop else 120
    if duration <= 0:
        return "unknown"

    progress = days_since_sowing / duration
    if progress < 0.15:
        return "establishment"
    if progress < 0.40:
        return "vegetative"
    if progress < 0.65:
        return "flowering"
    if progress < 0.90:
        return "grain_filling"
    if progress <= 1.15:
        return "maturity"
    return "past_harvest"


def _soil_warning(soil: Optional[SoilData], farm_input: FarmInput) -> Optional[str]:
    if soil is None:
        return (
            "No Soil Health Card record found for this location. "
            "Advice below uses crop-standard values, not your actual soil."
        )
    if soil.match_level == "district":
        return (
            f"No soil sample for PIN {farm_input.pincode}. "
            f"Using the average of {soil.records_averaged} sample(s) from {soil.district} district."
        )
    if soil.match_level == "state":
        return (
            f"No soil sample near PIN {farm_input.pincode}. "
            f"Using a {soil.state} state-level average - treat the numbers as indicative only."
        )
    return None


def aggregate_farm_data(farm_input: FarmInput, today: Optional[date] = None) -> AggregatedData:
    """
    Merge farmer input + soil card + weather + crop reference into one object.

    Never raises for missing data. Anything unavailable is recorded in
    `data_gaps` / `warnings` and left as None, so modules can decide for
    themselves whether to return "ok" or "partial".
    """
    today = today or date.today()
    data_gaps: list[str] = []
    warnings: list[str] = []

    # --- 1. location ------------------------------------------------------
    location = data_loader.resolve_location(
        pincode=farm_input.pincode,
        village=farm_input.village,
        latitude=farm_input.latitude,
        longitude=farm_input.longitude,
    )
    if not location.resolved:
        data_gaps.append("location")
        warnings.append(
            f"PIN code {farm_input.pincode} is not in our lookup table yet, "
            "so district-level data could not be attached."
        )

    # --- 2. soil ----------------------------------------------------------
    soil = data_loader.find_soil_record(
        pincode=farm_input.pincode,
        district=location.district,
        state=location.state,
    )
    if soil is None:
        data_gaps.append("soil_health_card")
    soil_warning = _soil_warning(soil, farm_input)
    if soil_warning:
        warnings.append(soil_warning)

    if farm_input.soil_test_available and soil is None:
        warnings.append(
            "You said a soil test is available. Ask your Krishi Vigyan Kendra to "
            "upload the card, or enter the values manually - accuracy will improve a lot."
        )

    # --- 3. weather -------------------------------------------------------
    # Live (Open-Meteo) - see services/weather.py. Still wrapped defensively:
    # unresolved coordinates or a network/API failure must never break the
    # rest of the farm request, only degrade this one source.
    try:
        weather = weather_service.get_weather(location, on_date=today)
    except Exception as exc:  # noqa: BLE001 - weather must never break aggregation
        weather = None
        data_gaps.append("weather")
        warnings.append(f"Weather lookup failed ({type(exc).__name__}). Rainfall advice is unavailable.")

    # --- 4. crop reference ------------------------------------------------
    crop_reference = data_loader.find_crop(farm_input.crop_name)
    if crop_reference is None:
        data_gaps.append("crop_reference")
        warnings.append(
            f"'{farm_input.crop_name}' is not in our ICAR crop table yet. "
            "Crop-specific advice will be generic."
        )

    # --- derived ----------------------------------------------------------
    days_since_sowing = (today - farm_input.sowing_date).days
    land_size_hectare = farm_input.land_size_hectare()

    land_unit = (
        farm_input.land_unit.value
        if hasattr(farm_input.land_unit, "value")
        else farm_input.land_unit
    )
    if land_unit == "bigha":
        warnings.append(
            "Bigha size varies by state. We assumed 1 bigha = 0.2529 hectare (UP/Bihar pucca bigha)."
        )

    resolved_sources = sum(
        [location.resolved, soil is not None, weather is not None, crop_reference is not None]
    )

    return AggregatedData(
        request_id=uuid.uuid4().hex[:12],
        farm_input=farm_input,
        land_size_hectare=land_size_hectare,
        days_since_sowing=days_since_sowing,
        crop_stage_hint=_crop_stage_hint(days_since_sowing, crop_reference),
        location=location,
        soil=soil,
        weather=weather,
        crop_reference=crop_reference,
        data_gaps=data_gaps,
        warnings=warnings,
        completeness=round(resolved_sources / 4, 2),
    )


def aggregate_as_module_response(aggregated: AggregatedData) -> ModuleResponse:
    """
    Wrap AggregatedData in the STEP 4 envelope so `/api/aggregate` looks
    exactly like every other endpoint to the frontend.
    """
    place = aggregated.location.district or aggregated.location.village or aggregated.location.pincode
    crop = aggregated.farm_input.crop_name

    if not aggregated.data_gaps:
        status: str = "ok"
        summary = f"Farm details ready for {crop} at {place}. All data sources found."
    else:
        status = "partial"
        readable = {
            "location": "location details",
            "soil_health_card": "soil card",
            "weather": "weather",
            "crop_reference": "crop guide",
        }
        missing = ", ".join(readable.get(gap, gap) for gap in aggregated.data_gaps)
        summary = f"Farm details ready for {crop} at {place}, but {missing} could not be found."

    return ModuleResponse(
        module_name=MODULE_NAME,
        status=status,  # type: ignore[arg-type]
        summary=summary,
        details=aggregated.model_dump(mode="json"),
        confidence=None,
        timestamp=aggregated.generated_at,
    )
