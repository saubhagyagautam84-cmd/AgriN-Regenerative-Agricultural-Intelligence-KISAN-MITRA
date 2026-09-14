"""
The Part B orchestrator - runs the DAG in the order the cross-module
dependencies require, and never lets one broken module take down the rest
(same philosophy as Part A's services/modules/__init__.py::run_module).

    1. Feature Resolver
    2. M2 Phase A (severity)              <- only needs soil
    3. M1 rotation                        <- reads M2's severity
    4. M4 cover-cropping                  <- independent
    5. M3 fertilizer                      <- independent
    6. M5 irrigation                      <- independent
    7. M2 Phase B (trend projection)      <- reads M1's + M4's picks
    8. Regeneration Score Engine          <- reads all five final outputs
"""

from __future__ import annotations

import traceback
from typing import Any, Callable

from models.schemas import AggregatedData, FarmInput, ModuleResponse, RegenAnalyzeResponse, RegenerationScore
from regeneration_score.adapters import adapt_all_modules
from regeneration_score.dynamic_weights import get_dynamic_weights
from regeneration_score.explainability import build_score_drivers
from regeneration_score.history_tracker import build_real_history, generate_farm_id, simulate_history
from regeneration_score.peer_comparison import build_peer_comparison
from regeneration_score.score_engine import compute_regeneration_score
from services import farmer_soil_observations, score_history
from services.regen import m1_rotation, m2_soil_carbon, m3_fertilizer, m4_cover_cropping, m5_irrigation
from services.regen.feature_resolver import build_enriched_feature_vector


def _contribute_farmer_soil_observation(farm_input: FarmInput, aggregated: AggregatedData) -> None:
    """
    The farmer-contributed soil data loop's write side: if the farmer typed
    in their own soil test values, persist them (geotagged via the location
    already resolved for this request) so they densify the block/district
    average other nearby farmers' estimates are built from - see
    services/farmer_soil_observations.py for the dedupe/disclosure rules.
    Never raises: a storage hiccup here must not break the farmer's own
    report, which is why this runs as a best-effort side effect, not
    something the response depends on.
    """
    if not farm_input.soil_test_available:
        return
    try:
        farmer_soil_observations.record_observation(
            pincode=farm_input.pincode,
            block=aggregated.location.block,
            district=aggregated.location.district,
            state=aggregated.location.state,
            n_kg_per_ha=farm_input.soil_test_n_kg_per_ha,
            p_kg_per_ha=farm_input.soil_test_p_kg_per_ha,
            k_kg_per_ha=farm_input.soil_test_k_kg_per_ha,
            ph=farm_input.soil_test_ph,
            organic_carbon_pct=farm_input.soil_test_organic_carbon_pct,
        )
    except Exception:  # noqa: BLE001 - best-effort; never break the farmer's own report over this
        pass


def _safe(name: str, fn: Callable[[], ModuleResponse]) -> ModuleResponse:
    """A broken module degrades its own block, never the whole pipeline."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return ModuleResponse.error(
            name,
            summary="This advice could not be prepared right now. Please try again.",
            details={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(limit=5),
            },
        )


def run_regen_pipeline(farm_input: FarmInput, aggregated: AggregatedData) -> RegenAnalyzeResponse:
    vector = build_enriched_feature_vector(farm_input, aggregated)
    _contribute_farmer_soil_observation(farm_input, aggregated)

    # --- 2. M2 severity (must run before M1) --------------------------------
    severity = m2_soil_carbon.compute_severity(vector)

    # --- 3-6. the four independent-at-runtime modules -----------------------
    m1_response = _safe("rotation", lambda: m1_rotation.run(vector, severity))
    m4_response = _safe("cover_cropping", lambda: m4_cover_cropping.run(vector))
    m3_response = _safe("fertilizer", lambda: m3_fertilizer.run(vector))
    m5_response = _safe("irrigation_efficiency", lambda: m5_irrigation.run(vector))

    # --- 7. M2 Phase B (needs M1's + M4's results) --------------------------
    m2_response = _safe(
        "soil_health",
        lambda: m2_soil_carbon.run(vector, severity, m1_response.details, m4_response.details),
    )

    # --- 8. Regeneration Score Engine (Part C) -------------------------------
    # A module in "error" status contributes None to the engine, which
    # triggers the all-5-missing null-score edge case only when every module
    # errored - a single failed module still produces a real score (see
    # regeneration_score/test_edge_cases.py::test_one_module_missing_still_scores).
    module_responses = {
        "M1_rotation": m1_response,
        "M2_soil_carbon": m2_response,
        "M3_fertilizer": m3_response,
        "M4_cover_crop": m4_response,
        "M5_irrigation": m5_response,
    }
    adapted = adapt_all_modules(
        vector, m1_response.details, m2_response.details, m3_response.details, m4_response.details, m5_response.details
    )
    adapted_or_none = {
        name: (None if module_responses[name].status == "error" else adapted[name]) for name in adapted
    }
    weights = get_dynamic_weights(
        water_source=farm_input.irrigation_source,
        has_soil_test=farm_input.soil_test_available,
    )
    score_result = compute_regeneration_score(adapted_or_none, weights=weights)

    # --- Steps 7-8: history (real once it exists, simulated for a farm_id's
    # first-ever submission) + explainability (only meaningful alongside a
    # real score) ---------------------------------------------------------
    history = None
    score_drivers = None
    peer_comparison = None
    if score_result["regeneration_score"] is not None:
        farm_id = generate_farm_id(farm_input.pincode, farm_input.crop_name)
        score_history.record_snapshot(
            farm_id, farm_input.pincode, farm_input.crop_name,
            score_result["regeneration_score"], score_result["confidence_level"],
            district=aggregated.location.district, state=aggregated.location.state,
        )
        prior_snapshots = score_history.get_prior_snapshots(farm_id)
        if prior_snapshots:
            history = build_real_history(farm_id, prior_snapshots, score_result["regeneration_score"])
        else:
            history = simulate_history(
                farm_id, score_result["regeneration_score"], m2_response.details.get("projection") or {}
            )
        score_drivers = build_score_drivers(
            m1_response.details, m3_response.details, m4_response.details, score_result["breakdown"]
        )
        peer_comparison = build_peer_comparison(
            farm_id, aggregated.location.district, score_result["regeneration_score"]
        )

    regen_score = RegenerationScore(
        score=score_result["regeneration_score"],
        confidence=score_result["confidence_level"],
        breakdown=score_result["breakdown"],
        score_tone=score_result.get("score_tone"),
        weakest_module=score_result.get("weakest_module"),
        improvement_tip=score_result.get("improvement_tip"),
        message=score_result.get("message"),
        history=history,
        score_drivers=score_drivers,
        peer_comparison=peer_comparison,
    )

    return RegenAnalyzeResponse(
        module_1_rotation=m1_response,
        module_2_soil_health=m2_response,
        module_3_fertilizer=m3_response,
        module_4_cover_cropping=m4_response,
        module_5_irrigation=m5_response,
        regeneration_score=regen_score,
    )
