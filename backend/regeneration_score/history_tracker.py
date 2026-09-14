"""
STEP 7 - history/trend, real once it exists, simulated until it does.

This project now DOES have persistence (services/auth.py's SQLite predates
this; services/score_history.py adds a `score_snapshots` table storing every
computed regen_score). So the original STEP 7 simulation below - reusing
M2's own 3-season projection output (services/regen/m2_soil_carbon.py) to
back-calculate a plausible "last season" point, no fabricated growth model -
is kept exactly as it was, but demoted to a FALLBACK: it only runs for a
farm_id's very first-ever submission, when no real prior snapshot exists to
show instead. See services/regen/pipeline.py for how the two are chosen
between - real data wins the moment it exists.

`farm_id` is a deterministic hash of (pincode, crop_name) - stable across
repeated submissions for what is plausibly "the same farm", without a real
account system (see services/score_history.py's own docstring on why this
is keyed by farm_id rather than logged-in user).

Both `build_real_history()` and `simulate_history()` return the same shape
plus a `"source"` field ("real" | "simulated") so a caller - or a future
dashboard - can tell honestly which one it's looking at.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any, Sequence


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
        "source": "simulated",
    }


def build_real_history(farm_id: str, prior_snapshots: Sequence[Any], current_score: float) -> dict[str, Any]:
    """
    Real season-over-season history from actual stored score_snapshots rows
    (services/score_history.py) - used whenever at least one real prior
    submission exists for this farm_id, taking priority over the simulated
    fallback above.

    `prior_snapshots` must be newest-first (score_history.get_prior_snapshots'
    own ordering) and non-empty.
    """
    chronological = list(reversed(prior_snapshots))  # oldest first, for the trend line
    points = [
        {"date": date.fromtimestamp(row["created_at"]).isoformat(), "score": row["regen_score"]}
        for row in chronological
    ]
    points.append({"date": date.today().isoformat(), "score": current_score})

    most_recent_prior = prior_snapshots[0]["regen_score"]
    delta = round(current_score - most_recent_prior, 1)
    sign = "+" if delta >= 0 else ""

    return {
        "farm_id": farm_id,
        "history": points,
        "trend": f"{sign}{delta} points since your last check",
        "source": "real",
    }
