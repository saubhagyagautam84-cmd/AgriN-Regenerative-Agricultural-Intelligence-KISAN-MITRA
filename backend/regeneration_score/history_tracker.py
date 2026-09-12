"""
STEP 7 (nice-to-have) - simulated history/trend.

Per the confirmed decision: this project has explicitly documented "no
database, no auth, no persistence" up to now - adding real longitudinal
storage would be a genuine architecture change, not a Part C concern.
Instead, exactly as the spec suggests, the "trend" is simulated by reusing
M2's own 3-season projection output (services/regen/m2_soil_carbon.py) -
no new logic invented, no fabricated growth model.

`farm_id` is a deterministic hash of (pincode, crop_name) - stable across
repeated submissions for what is plausibly "the same farm", without a real
account system. `history` is NOT read from storage (there isn't any): the
"last season" point is back-calculated from the CURRENT actual regen_score
using the season-over-season growth RATE M2's regenerative_practice
trajectory already computed. This is honestly a simulation for the demo,
not a real historical record - documented as such rather than presented
as if real data was tracked.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any


def generate_farm_id(pincode: str, crop_name: str) -> str:
    """Deterministic, not random - the same farm+crop always gets the same id, with no account system needed."""
    key = f"{pincode.strip()}:{crop_name.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def simulate_history(
    farm_id: str,
    current_score: float,
    m2_projection: dict[str, list[dict[str, Any]]],
    days_per_season: int = 90,
) -> dict[str, Any]:
    """
    Back-calculates a plausible "last season" score from the CURRENT
    regen_score using M2's regenerative_practice growth rate - reusing that
    module's own numbers rather than inventing a new trend model.
    """
    regen_trajectory = m2_projection.get("regenerative_practice") or []
    if len(regen_trajectory) >= 2:
        first = regen_trajectory[0]["soil_health_score"]
        last = regen_trajectory[-1]["soil_health_score"]
        seasons_spanned = len(regen_trajectory) - 1
        if first > 0 and seasons_spanned > 0:
            growth_rate = (last / first) ** (1 / seasons_spanned) - 1
        else:
            growth_rate = 0.0
    else:
        growth_rate = 0.0

    last_season_score = round(current_score / (1 + growth_rate), 1) if (1 + growth_rate) > 0 else current_score
    last_season_score = max(0.0, min(100.0, last_season_score))

    today = date.today()
    last_season_date = today - timedelta(days=days_per_season)
    delta = round(current_score - last_season_score, 1)
    sign = "+" if delta >= 0 else ""

    return {
        "farm_id": farm_id,
        "history": [
            {"date": last_season_date.isoformat(), "score": last_season_score},
            {"date": today.isoformat(), "score": current_score},
        ],
        "trend": f"{sign}{delta} points since last season",
    }
