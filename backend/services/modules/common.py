"""
Shared agronomy constants and helpers for the four modules.

Every number in this file is a rule of thumb, not a model output. They exist
so the skeleton produces believable data for the demo. Each one is a
candidate for replacement by a trained model or an agronomist's table.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from models.schemas import Season

# --------------------------------------------------------------------------
# Soil Health Card rating bands (Government of India SHC scheme)
# These ones are real, not invented - keep them if you swap in ML.
# --------------------------------------------------------------------------

# field -> ((low_max, medium_max), unit, human label)
SHC_RATING_BANDS: dict[str, tuple[tuple[float, float], str, str]] = {
    "n_kg_per_ha": ((280.0, 560.0), "kg/ha", "Nitrogen (N)"),
    "p_kg_per_ha": ((10.0, 25.0), "kg/ha", "Phosphorus (P)"),
    "k_kg_per_ha": ((108.0, 280.0), "kg/ha", "Potassium (K)"),
    "organic_carbon_pct": ((0.50, 0.75), "%", "Organic carbon"),
    "s_ppm": ((10.0, 20.0), "ppm", "Sulphur (S)"),
    "zn_ppm": ((0.60, 1.20), "ppm", "Zinc (Zn)"),
    "fe_ppm": ((4.50, 9.00), "ppm", "Iron (Fe)"),
    "cu_ppm": ((0.20, 0.40), "ppm", "Copper (Cu)"),
    "mn_ppm": ((2.00, 4.00), "ppm", "Manganese (Mn)"),
    "b_ppm": ((0.50, 1.00), "ppm", "Boron (B)"),
}

RATING_LABELS_HI: dict[str, str] = {
    "low": "कम",
    "medium": "ठीक",
    "high": "ज़्यादा",
}


def rate_nutrient(field: str, value: Optional[float]) -> Optional[str]:
    """Return 'low' | 'medium' | 'high' for a soil measurement."""
    if value is None or field not in SHC_RATING_BANDS:
        return None
    (low_max, medium_max), _unit, _label = SHC_RATING_BANDS[field]
    if value < low_max:
        return "low"
    if value <= medium_max:
        return "medium"
    return "high"


def describe_ph(ph: Optional[float]) -> tuple[str, str]:
    """(machine_code, farmer-readable phrase) for a pH value."""
    if ph is None:
        return "unknown", "Soil pH is not known"
    if ph < 5.5:
        return "strongly_acidic", "Soil is strongly acidic - lime is usually needed"
    if ph < 6.5:
        return "slightly_acidic", "Soil is slightly acidic - fine for most crops"
    if ph <= 7.5:
        return "neutral", "Soil pH is normal - good for most crops"
    if ph <= 8.5:
        return "alkaline", "Soil is alkaline - zinc and iron may get locked up"
    return "strongly_alkaline", "Soil is strongly alkaline - gypsum treatment is usually needed"


def describe_ec(ec: Optional[float]) -> tuple[str, str]:
    if ec is None:
        return "unknown", "Salinity not known"
    if ec < 1.0:
        return "normal", "Salt level is normal"
    if ec < 2.0:
        return "slightly_saline", "Slightly salty - sensitive crops may suffer"
    return "saline", "Salty soil - choose salt-tolerant crops and improve drainage"


# --------------------------------------------------------------------------
# Irrigation
# --------------------------------------------------------------------------

# Roughly how much supplemental water a source can realistically deliver over
# one season, in mm. TODO(agronomy): should vary by district groundwater
# status and canal release schedule.
IRRIGATION_CAPACITY_MM: dict[str, float] = {
    "rainfed": 0.0,
    "canal": 500.0,
    "borewell": 900.0,
    "tubewell": 900.0,
    "tank_pond": 400.0,
    "drip_sprinkler": 700.0,
    "other": 400.0,
}

# Application efficiency - how much of the water applied reaches the root zone.
IRRIGATION_EFFICIENCY: dict[str, float] = {
    "rainfed": 1.0,
    "canal": 0.55,
    "borewell": 0.65,
    "tubewell": 0.65,
    "tank_pond": 0.55,
    "drip_sprinkler": 0.90,
    "other": 0.60,
}

IRRIGATION_LABELS: dict[str, str] = {
    "rainfed": "Rain-fed",
    "canal": "Canal",
    "borewell": "Borewell",
    "tubewell": "Tubewell",
    "tank_pond": "Tank / pond",
    "drip_sprinkler": "Drip / sprinkler",
    "other": "Other",
}

# Crop coefficient (Kc) by growth stage - multiplies ET0 to get crop demand.
STAGE_CROP_COEFFICIENT: dict[str, float] = {
    "not_sown_yet": 0.0,
    "establishment": 0.45,
    "vegetative": 0.80,
    "flowering": 1.15,
    "grain_filling": 1.00,
    "maturity": 0.60,
    "past_harvest": 0.0,
    "unknown": 0.85,
}


# --------------------------------------------------------------------------
# Seasons
# --------------------------------------------------------------------------


def season_for_month(month: int) -> Season:
    """Indian cropping calendar."""
    if month in (6, 7, 8, 9, 10):
        return Season.KHARIF
    if month in (11, 12, 1, 2, 3):
        return Season.RABI
    return Season.ZAID  # April - May


def next_season(today: Optional[date] = None) -> tuple[Season, str]:
    """The season a farmer would plant next, plus a readable window."""
    today = today or date.today()
    current = season_for_month(today.month)
    if current == Season.KHARIF:
        return Season.RABI, "Rabi (sowing from late October)"
    if current == Season.RABI:
        return Season.ZAID, "Zaid (sowing from March)"
    return Season.KHARIF, "Kharif (sowing with the monsoon, June onward)"


SEASON_LABELS: dict[str, str] = {
    "kharif": "Kharif (monsoon)",
    "rabi": "Rabi (winter)",
    "zaid": "Zaid (summer)",
    "perennial": "Year-round",
}

# Rough seasonal rainfall a farm can expect, in mm, before any irrigation.
SEASON_RAINFALL_MM: dict[str, float] = {
    "kharif": 650.0,
    "rabi": 90.0,
    "zaid": 45.0,
    "perennial": 800.0,
}


def litres_for(depth_mm: float, hectares: float) -> int:
    """1 mm of water over 1 hectare = 10,000 litres."""
    return int(round(depth_mm * hectares * 10_000))


def as_value(enum_or_str) -> str:
    """Enums are configured with use_enum_values, but be defensive."""
    return enum_or_str.value if hasattr(enum_or_str, "value") else str(enum_or_str)
