"""
STEP 3 - confidence-weighted scoring.

A module's score is only as trustworthy as the data it was computed from.
This file turns each module's `confidence_source` (traced back to the
Feature Resolver - see adapters.py) into a multiplier applied to that
module's normalized score BEFORE the weighted average, so two farms with
identical raw scores but different data quality get different final
numbers - not just different confidence labels bolted on afterward.
"""

from __future__ import annotations

CONFIDENCE_MULTIPLIER: dict[str, float] = {
    "observed": 1.0,  # real farmer-entered data, or an exact Soil Health Card match
    "district_avg": 0.8,  # Soil Health Card fallback - district or state average
    "estimated": 0.6,  # no match at all - a crop-standard default was assumed
}


def weighted_module_score(score: float, confidence_source: str) -> float:
    if confidence_source not in CONFIDENCE_MULTIPLIER:
        raise ValueError(f"unknown confidence_source: {confidence_source!r}")
    return round(score * CONFIDENCE_MULTIPLIER[confidence_source], 2)
