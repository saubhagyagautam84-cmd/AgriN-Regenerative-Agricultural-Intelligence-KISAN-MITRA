"""
STEP 4 - combines Steps 1-3 into the full Output Contract object.

The single entry point this whole package exists for: `compute_regeneration_score()`.
Takes the standardized per-module input (see adapters.py) and static weights
(dynamic_weights.py replaces the static ones in Step 6), returns the full
breakdown object - never a bare number, per the spec.

Edge cases (Step 5) are handled here too: insufficient data returns `null` +
a message instead of fabricating a score; a 95+ score gets capped messaging
tone; conflicting modules are surfaced explicitly rather than hidden by
averaging.
"""

from __future__ import annotations

from typing import Any, Optional

from regeneration_score.confidence import CONFIDENCE_MULTIPLIER, weighted_module_score

STATIC_WEIGHTS: dict[str, float] = {
    "M1_rotation": 0.20,
    "M2_soil_carbon": 0.25,
    "M3_fertilizer": 0.25,
    "M4_cover_crop": 0.15,
    "M5_irrigation": 0.15,
}

# A generic "good" target used to simulate the improvement_tip's point delta -
# not a per-module tuned number, just "what would a solidly healthy score
# look like for any module", since raw_score is already normalized to 0-100.
GOOD_TARGET_SCORE = 85.0

TIP_TEMPLATES: dict[str, str] = {
    "M1_rotation": "Following a stronger crop rotation plan could raise your score by ~{delta} points",
    "M2_soil_carbon": "Improving soil organic carbon (compost/FYM) could raise your score by ~{delta} points",
    "M3_fertilizer": "Following the recommended fertiliser dose more closely could raise your score by ~{delta} points",
    "M4_cover_crop": "Adding a cover crop this season could raise your score by ~{delta} points",
    "M5_irrigation": "Switching to a more water-efficient irrigation schedule could raise your score by ~{delta} points",
}

# A "conflict" is flagged when two modules' scores are far enough apart that
# a plain weighted average would quietly smooth over a real disagreement
# (one part of the farm regenerating well, another badly).
CONFLICT_GAP_THRESHOLD = 40.0


def _compute_total(adapted_modules: dict[str, dict[str, Any]], weights: dict[str, float]) -> float:
    total = 0.0
    for module_name, weight in weights.items():
        module = adapted_modules[module_name]
        adjusted = weighted_module_score(module["raw_score"], module["confidence_source"])
        total += adjusted * weight
    return round(max(0.0, min(100.0, total)), 1)


def _overall_confidence_level(adapted_modules: dict[str, dict[str, Any]]) -> str:
    sources = {m["confidence_source"] for m in adapted_modules.values()}
    return "High" if sources == {"observed"} else "Estimated"


def _find_weakest_module(adapted_modules: dict[str, dict[str, Any]]) -> str:
    """Lowest CONFIDENCE-ADJUSTED sub-score, not just lowest raw score - per spec."""
    def adjusted_score(module: dict[str, Any]) -> float:
        return weighted_module_score(module["raw_score"], module["confidence_source"])

    return min(adapted_modules, key=lambda name: adjusted_score(adapted_modules[name]))


CONFIDENCE_TIP_TEMPLATE = (
    "{module}'s reading is already good but based on {confidence} data - a real "
    "soil test or on-farm confirmation there could raise your score by ~{delta} points"
)


def _simulate_improvement_tip(
    adapted_modules: dict[str, dict[str, Any]],
    weights: dict[str, float],
    weakest_module: str,
    current_score: float,
) -> str:
    """
    Recompute regen_score with the weakest module improved - the delta is
    real, not hardcoded. "Weakest" is picked by CONFIDENCE-ADJUSTED score
    (per spec), which means the actual lever worth simulating depends on
    WHY it's weakest:

      - raw_score is genuinely low -> simulate raising the raw score to
        GOOD_TARGET_SCORE (the module's real reading needs to improve).
      - raw_score is already good but confidence is low (estimated/
        district_avg) -> simulate raising CONFIDENCE to "observed" instead.
        Bumping an already-good raw_score toward GOOD_TARGET_SCORE here
        would produce a NEGATIVE delta (a nonsensical "raise your score by
        ~-3 points") - this branch is what fixes that.
    """
    simulated = {name: dict(module) for name, module in adapted_modules.items()}
    current_module = adapted_modules[weakest_module]

    if current_module["raw_score"] < GOOD_TARGET_SCORE:
        simulated[weakest_module]["raw_score"] = GOOD_TARGET_SCORE
        simulated_score = _compute_total(simulated, weights)
        delta = round(simulated_score - current_score, 1)
        template = TIP_TEMPLATES.get(weakest_module, "Improving {module} could raise your score by ~{delta} points")
        return template.format(module=weakest_module, delta=delta)

    # Raw score is already at/above target - the real lever is confidence.
    simulated[weakest_module]["confidence_source"] = "observed"
    simulated_score = _compute_total(simulated, weights)
    delta = round(simulated_score - current_score, 1)
    if delta <= 0:
        return f"{weakest_module.replace('_', ' ')} is already performing well with solid data - no urgent action needed."
    return CONFIDENCE_TIP_TEMPLATE.format(
        module=weakest_module.replace("_", " "), confidence=current_module["confidence_source"].replace("_", " "), delta=delta
    )


def _detect_conflicts(adapted_modules: dict[str, dict[str, Any]]) -> list[str]:
    """Module pairs whose raw scores disagree enough that averaging would hide a real conflict."""
    names = list(adapted_modules)
    conflicts = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            gap = abs(adapted_modules[a]["raw_score"] - adapted_modules[b]["raw_score"])
            if gap >= CONFLICT_GAP_THRESHOLD:
                conflicts.append(f"{a} ({adapted_modules[a]['raw_score']}) vs {b} ({adapted_modules[b]['raw_score']}) - a {gap:.0f}-point gap")
    return conflicts


def _score_tone(score: float) -> str:
    if score >= 95:
        return "excellent - minor room for improvement"
    if score >= 80:
        return "very good"
    if score >= 60:
        return "good, with room to improve"
    if score >= 40:
        return "needs attention"
    return "needs significant improvement"


def compute_regeneration_score(
    adapted_modules: dict[str, dict[str, Any]],
    weights: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    weights = weights or STATIC_WEIGHTS
    weight_sum = round(sum(weights.values()), 6)
    if weight_sum != 1.0:
        raise ValueError(f"weights must sum to 1.0, got {weight_sum}")

    # --- Step 5 edge case: all 5 modules failed -> never fabricate a score ---
    failed = [name for name, m in adapted_modules.items() if m is None]
    if len(failed) == len(weights):
        return {
            "regeneration_score": None,
            "confidence_level": None,
            "breakdown": None,
            "message": "Insufficient data - please complete soil test",
        }

    # Modules that DID fail (but not all) contribute 0 rather than crashing -
    # never let one broken module take down the whole score.
    safe_modules = {
        name: (m if m is not None else {"raw_score": 0.0, "confidence_source": "estimated"})
        for name, m in adapted_modules.items()
    }

    regen_score = _compute_total(safe_modules, weights)
    confidence_level = _overall_confidence_level(safe_modules)
    weakest_module = _find_weakest_module(safe_modules)
    improvement_tip = _simulate_improvement_tip(safe_modules, weights, weakest_module, regen_score)
    conflicts = _detect_conflicts(safe_modules)

    breakdown = {
        name: {
            "score": module["raw_score"],
            "weight": weights[name],
            "confidence": module["confidence_source"],
        }
        for name, module in safe_modules.items()
    }
    if conflicts:
        breakdown["_conflicts"] = conflicts

    return {
        "regeneration_score": regen_score,
        "confidence_level": confidence_level,
        "score_tone": _score_tone(regen_score),
        "breakdown": breakdown,
        "weakest_module": weakest_module,
        "improvement_tip": improvement_tip,
    }
