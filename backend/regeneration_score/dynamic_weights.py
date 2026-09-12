"""
STEP 6 (nice-to-have) - dynamic weight adjustment.

Replaces score_engine.py's STATIC_WEIGHTS, not a duplicate of it - only
wired in once the static version was fully tested (Steps 1-5 above).

Note: this project's actual FarmInput.irrigation_source enum uses
"rainfed" (see backend/models/schemas.py), not the spec's "rain_only" -
same field, same intent, matching the value this codebase already
established back in Part B.
"""

from __future__ import annotations


def get_dynamic_weights(water_source: str, has_soil_test: bool) -> dict[str, float]:
    weights = {"M1_rotation": 0.20, "M2_soil_carbon": 0.25, "M3_fertilizer": 0.25, "M4_cover_crop": 0.15, "M5_irrigation": 0.15}
    if water_source == "rainfed":
        weights["M5_irrigation"] -= 0.10
        weights["M2_soil_carbon"] += 0.05
        weights["M4_cover_crop"] += 0.05
    if not has_soil_test:
        weights["M3_fertilizer"] -= 0.05
        weights["M1_rotation"] += 0.05

    weights = {name: round(value, 6) for name, value in weights.items()}
    total = round(sum(weights.values()), 6)
    if total != 1.0:
        raise ValueError(f"dynamic weights must sum to 1.0, got {total} for {weights}")
    return weights
