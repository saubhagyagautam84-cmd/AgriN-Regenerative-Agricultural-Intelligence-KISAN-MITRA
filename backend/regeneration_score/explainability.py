"""
STEP 8 (nice-to-have) - explainability output.

Surfaces EXISTING module internals as a ranked, farmer-readable list - no
new ML model, no new scoring logic. Each driver's "impact" is the module's
actual confidence-weighted contribution to regen_score, relative to what a
neutral (score=50) module would have contributed - reusing Step 3's own
weighted_module_score() math, just referenced against a midpoint instead
of zero. That makes the number real and traceable, not invented for
display purposes.

Pulls from:
  - M1's rotation reasoning (services/regen/m1_rotation.py's `reasons`)
  - M3's feature-importance explanation (services/regen/m3_fertilizer.py's `explanation`)
  - M4's cover-crop pick (services/regen/m4_cover_cropping.py's `cover_crop_suggestions`)

(The spec's prose calls out M1+M3 specifically; its own example output
also shows a cover-crop driver, so M4 is included too - cover cropping is
central to what this whole engine is regenerating.)
"""

from __future__ import annotations

from typing import Any

from regeneration_score.confidence import CONFIDENCE_MULTIPLIER


def _baseline_relative_impact(raw_score: float, weight: float, confidence_source: str) -> float:
    """This module's actual weighted contribution to regen_score, minus what a neutral (50) module would give."""
    multiplier = CONFIDENCE_MULTIPLIER[confidence_source]
    actual = raw_score * multiplier * weight
    neutral = 50.0 * multiplier * weight
    return round(actual - neutral, 1)


def _format_impact(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:g}"


def _m1_driver(m1_details: dict[str, Any], breakdown_entry: dict[str, Any]) -> dict[str, str] | None:
    suggestions = m1_details.get("next_crop_suggestions") or []
    if not suggestions:
        return None
    top = suggestions[0]
    is_legume_pick = bool(top.get("is_legume"))
    factor = "Good crop rotation history" if is_legume_pick else "Rotation could include more nitrogen-fixers"
    impact = _baseline_relative_impact(breakdown_entry["score"], breakdown_entry["weight"], breakdown_entry["confidence"])
    return {"factor": factor, "impact": _format_impact(impact)}


def _m3_driver(m3_details: dict[str, Any], breakdown_entry: dict[str, Any]) -> dict[str, str] | None:
    if m3_details.get("reduction_percent") is None:
        return None
    reduction_percent = m3_details["reduction_percent"]
    factor = "Low fertilizer overuse" if reduction_percent >= 0 else "Fertiliser under-application (especially potash)"
    impact = _baseline_relative_impact(breakdown_entry["score"], breakdown_entry["weight"], breakdown_entry["confidence"])
    return {"factor": factor, "impact": _format_impact(impact)}


def _m4_driver(m4_details: dict[str, Any], breakdown_entry: dict[str, Any]) -> dict[str, str] | None:
    suggestions = m4_details.get("cover_crop_suggestions") or []
    if not suggestions:
        factor = "No cover crop planted"
    else:
        top = suggestions[0]
        factor = "Strong cover-crop plan" if top.get("nitrogen_fixing_speed") == "fast" else "Cover-crop plan could fix nitrogen faster"
    impact = _baseline_relative_impact(breakdown_entry["score"], breakdown_entry["weight"], breakdown_entry["confidence"])
    return {"factor": factor, "impact": _format_impact(impact)}


def build_score_drivers(
    m1_details: dict[str, Any],
    m3_details: dict[str, Any],
    m4_details: dict[str, Any],
    breakdown: dict[str, dict[str, Any]],
    max_drivers: int = 3,
) -> list[dict[str, str]]:
    """Ranked by absolute impact, largest first - reuses breakdown's already-computed score/weight/confidence per module."""
    candidates = [
        _m1_driver(m1_details, breakdown["M1_rotation"]),
        _m3_driver(m3_details, breakdown["M3_fertilizer"]),
        _m4_driver(m4_details, breakdown["M4_cover_crop"]),
    ]
    drivers = [d for d in candidates if d is not None]
    drivers.sort(key=lambda d: abs(float(d["impact"])), reverse=True)
    return drivers[:max_drivers]
