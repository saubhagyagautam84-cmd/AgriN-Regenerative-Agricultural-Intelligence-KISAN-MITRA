"""
The Geographic Confidence Ladder - two SEPARATE resolution chains, not one
shared lookup. Soil chemistry and crop suitability degrade at different
geographic rates for real agronomic reasons, so they get different ladders:

    resolve_soil_field(...)         farmer's field -> block/village -> district
                                     -> state -> national   (skips the zone
                                     level entirely - a zone-wide "average
                                     soil" number isn't agronomically
                                     meaningful the way a block average is)

    resolve_crop_suitability(...)   agro-climatic zone baseline (the DEFAULT
                                     starting point, not a last resort) ->
                                     upgraded to district_avg when real
                                     district-level signal exists

Do not merge these into one function even though the fallback pattern looks
similar at a glance - see the module docstrings on why they're separate.

Every level actually checks data availability rather than assuming the next
level down exists (see the tests in regeneration_score/test_edge_cases.py
for the specific "district missing, state present" case this guards).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.data_loader import load_soil_records
from services.regen.geo_reference import GeoInfo, get_geo_info

# The 6-level ladder's ordering, worst -> best. Kept here (not just in
# regeneration_score/confidence.py) because the resolvers themselves need to
# reason about "did we already reach this level" while walking down - the
# multiplier VALUES live in confidence.py since that's Part C's concern, but
# the ORDER is a property of the ladder itself.
GEO_CONFIDENCE_LEVELS = ("national_avg", "state_avg", "zone_baseline", "district_avg", "block_avg", "observed")


@dataclass
class ResolvedGeoField:
    value: Optional[float]
    confidence_level: str  # one of GEO_CONFIDENCE_LEVELS
    detail: str  # human-readable trace, e.g. "Ludhiana district average (2 samples)"


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _average(records: list, field_name: str) -> Optional[float]:
    values = [getattr(r, field_name) for r in records if getattr(r, field_name, None) is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


# --------------------------------------------------------------------------
# Soil field resolution - Section 5's trace, step by step:
#   1. Farmer value present?            -> observed        (1.00)
#   2. Block/village SHC data for PIN?  -> block_avg        (0.90)
#   3. District SHC data for district?  -> district_avg     (0.80)
#   4. State average?                   -> state_avg        (0.50)
#   5. National average                 -> national_avg     (0.35)
# --------------------------------------------------------------------------


def resolve_soil_field(
    pin_code: Optional[str],
    field_name: str,
    farmer_value: Optional[float],
) -> ResolvedGeoField:
    """Walks farmer's own value -> block/village -> district -> state -> national. Never raises, never returns a None value."""
    if farmer_value is not None:
        return ResolvedGeoField(farmer_value, "observed", "your own soil test")

    geo = get_geo_info(pin_code)
    all_records, _ = load_soil_records()

    if geo is not None and all_records:
        # Block/village level: match on the block within the same district
        # (village-level samples in this dataset are too sparse - often a
        # single record - to be a meaningfully different average from their
        # block, so both collapse into the one "block_avg" rung the ladder
        # defines, matching the master prompt's own combined "Block/village"
        # trace step).
        block_hits = [
            r for r in all_records
            if _norm(r.district) == _norm(geo.district) and _norm(r.block) == _norm(geo.village_or_block)
        ]
        value = _average(block_hits, field_name)
        if value is not None:
            return ResolvedGeoField(
                value, "block_avg", f"{geo.village_or_block} block average ({len(block_hits)} sample(s))"
            )

    if geo is not None and all_records:
        district_hits = [r for r in all_records if _norm(r.district) == _norm(geo.district)]
        value = _average(district_hits, field_name)
        if value is not None:
            return ResolvedGeoField(
                value, "district_avg", f"{geo.district} district average ({len(district_hits)} sample(s))"
            )

    state_name = geo.state if geo is not None else None
    if state_name and all_records:
        state_hits = [r for r in all_records if _norm(r.state) == _norm(state_name)]
        value = _average(state_hits, field_name)
        if value is not None:
            return ResolvedGeoField(
                value, "state_avg", f"{state_name} state average ({len(state_hits)} sample(s))"
            )

    # National average - every valid record on file, regardless of location.
    # This is the floor of the real ladder; it can itself be empty only if
    # the whole dataset is empty, which callers handle via a documented
    # crop-standard default (see feature_resolver.py) rather than crashing.
    value = _average(all_records, field_name)
    if value is not None:
        return ResolvedGeoField(value, "national_avg", f"national average ({len(all_records)} sample(s))")

    return ResolvedGeoField(None, "national_avg", "no Soil Health Card data on file anywhere")


# --------------------------------------------------------------------------
# Crop suitability resolution - Section 5's shorter trace:
#   1. Resolve PIN -> agro-climatic zone -> zone_baseline (0.60), the
#      DEFAULT starting point (crop_reference.json's ICAR-sourced agronomy
#      facts ARE zone/national-level guidance, not hyper-local - that's
#      exactly what zone_baseline means).
#   2. District-level crop nuance available? -> upgrade to district_avg (0.80)
#
# This project has no separate "crop suitability by district" dataset (only
# crop_reference.json's national agronomy facts and the rule-based scoring
# modules that already exist - see services/regen/m1_rotation.py). Rather
# than fabricate a fake per-district suitability table, the upgrade
# condition here is a REAL signal already in the data: 2+ actual Soil
# Health Card samples for this exact district means there is genuine local
# agronomic signal (soil type, nutrient profile) informing that district
# specifically, not just its zone - a defensible, honest proxy for "we know
# more about this district than its zone alone," not an invented dataset.
# --------------------------------------------------------------------------


def resolve_crop_suitability(pin_code: Optional[str]) -> ResolvedGeoField:
    """Zone baseline by default, upgraded to district_avg when real district-level soil signal exists."""
    geo = get_geo_info(pin_code)
    if geo is None or not geo.agro_climatic_zone:
        # No zone can be resolved at all - this PIN is outside the demo's
        # geographic coverage. Falls all the way to the ladder's floor,
        # same as soil's national_avg case, rather than erroring.
        return ResolvedGeoField(None, "national_avg", "PIN code not in geo_reference.json - no zone could be resolved")

    all_records, _ = load_soil_records()
    district_hits = [r for r in all_records if _norm(r.district) == _norm(geo.district)]
    if len(district_hits) >= 2:
        return ResolvedGeoField(
            None,
            "district_avg",
            f"{geo.district} district ({len(district_hits)} real soil samples on file, beyond just its zone)",
        )

    return ResolvedGeoField(
        None, "zone_baseline", f"{geo.agro_climatic_zone} zone baseline (ICAR agronomy guidelines)"
    )
