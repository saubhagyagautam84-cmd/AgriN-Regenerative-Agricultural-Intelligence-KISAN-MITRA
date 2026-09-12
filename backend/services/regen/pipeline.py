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

from models.schemas import AggregatedData, FarmInput, ModuleResponse, RegenAnalyzeResponse
from services.regen import m1_rotation, m2_soil_carbon, m3_fertilizer, m4_cover_cropping, m5_irrigation
from services.regen.feature_resolver import build_enriched_feature_vector
from services.regen.regen_score import compute_regeneration_score


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

    # --- 8. Regeneration Score Engine ---------------------------------------
    regen_score = compute_regeneration_score(
        farm_input,
        vector,
        m1_response.details,
        m2_response.details,
        m3_response.details,
        m4_response.details,
        m5_response.details,
    )

    return RegenAnalyzeResponse(
        module_1_rotation=m1_response,
        module_2_soil_health=m2_response,
        module_3_fertilizer=m3_response,
        module_4_cover_cropping=m4_response,
        module_5_irrigation=m5_response,
        regeneration_score=regen_score,
    )
