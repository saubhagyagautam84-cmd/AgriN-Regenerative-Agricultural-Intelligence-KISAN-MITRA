"""
STEP 3 - confidence-weighted scoring.

A module's score is only as trustworthy as the data it was computed from.
This file turns each module's `confidence_source` (traced back to the
Geographic Confidence Ladder - see services/regen/geo_resolvers.py and
adapters.py) into a multiplier applied to that module's normalized score
BEFORE the weighted average, so two farms with identical raw scores but
different data quality get different final numbers - not just different
confidence labels bolted on afterward.

Replaces the old flat 3-tier system (observed/district_avg/estimated) with
a 6-level geographic ladder, because soil data and crop-suitability data
degrade at different rates for real agronomic reasons - see
services/regen/geo_resolvers.py's module docstring for why soil and crop
suitability get separate resolution chains feeding into this one shared
multiplier scale.
"""

from __future__ import annotations

GEOGRAPHIC_CONFIDENCE_MULTIPLIER: dict[str, float] = {
    "national_avg": 0.35,  # Level 0 - no location-specific signal at all
    "state_avg": 0.50,  # Level 1
    "zone_baseline": 0.60,  # Level 2 - crop suitability's natural home level
    "district_avg": 0.80,  # Level 3
    "block_avg": 0.90,  # Level 4
    "observed": 1.00,  # Level 5 - farmer's own data
}

# Numeric rank matching the table above, worst -> best - lets callers ask
# "which of these confidence_sources is weakest" without re-deriving order
# from the dict's insertion position.
GEO_CONFIDENCE_RANK: dict[str, int] = {
    name: rank for rank, name in enumerate(GEOGRAPHIC_CONFIDENCE_MULTIPLIER)
}


def weighted_module_score(score: float, confidence_source: str) -> float:
    if confidence_source not in GEOGRAPHIC_CONFIDENCE_MULTIPLIER:
        raise ValueError(f"unknown confidence_source: {confidence_source!r}")
    return round(score * GEOGRAPHIC_CONFIDENCE_MULTIPLIER[confidence_source], 2)
