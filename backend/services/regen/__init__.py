"""
Part B - the Regenerative Intelligence Engine.

    FORM INPUT (Part A's FarmInput)
            v
    Part A's aggregate_farm_data()   -> AggregatedData (location/soil/weather/crop)
            v
    build_enriched_feature_vector()  -> EnrichedFeatureVector  (feature_resolver.py)
            v
    M2 severity (phase A)  -> soil-depletion severity, read by M1
            v
    M1 rotation | M4 cover-cropping | M3 fertilizer | M5 irrigation
            v
    M2 trend projection (phase B) - reads M1's rotation pick + M4's cover crops
            v
    regeneration_score()             -> RegenerationScore   (regen_score.py)

`run_regen_pipeline()` is the single entry point main.py calls. It never
raises - a broken module degrades its own block of the output, exactly like
Part A's run_module().
"""

from __future__ import annotations

from services.regen.pipeline import run_regen_pipeline

__all__ = ["run_regen_pipeline"]
