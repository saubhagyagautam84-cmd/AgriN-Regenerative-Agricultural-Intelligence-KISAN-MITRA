"""
The module registry.

To add a fifth module (pest risk, yield forecast, market price...):

    1. create services/modules/my_module.py with
           run(aggregated: AggregatedData) -> ModuleResponse
    2. add it to MODULE_RUNNERS below
    3. that's it - `/api/analyze` picks it up and the dashboard renders it
       with the same card component. No frontend change required.
"""

from __future__ import annotations

import traceback
from typing import Callable

from models.schemas import AggregatedData, ModuleResponse
from services.modules import crop_recommendation, irrigation, rotation, soil_status

ModuleRunner = Callable[[AggregatedData], ModuleResponse]

MODULE_RUNNERS: dict[str, ModuleRunner] = {
    "soil_status": soil_status.run,
    "irrigation_advice": irrigation.run,
    "crop_recommendation": crop_recommendation.run,
    "rotation_suggestion": rotation.run,
}

# Order the dashboard renders them in.
MODULE_ORDER: list[str] = [
    "soil_status",
    "irrigation_advice",
    "crop_recommendation",
    "rotation_suggestion",
]


def run_module(name: str, aggregated: AggregatedData) -> ModuleResponse:
    """
    Run one module, converting any crash into a well-formed error response.

    A broken module must degrade its own card, never the whole dashboard -
    that matters most once real ML code starts landing here.
    """
    runner = MODULE_RUNNERS.get(name)
    if runner is None:
        return ModuleResponse.error(name, summary=f"Unknown module '{name}'.")

    try:
        return runner(aggregated)
    except Exception as exc:  # noqa: BLE001
        return ModuleResponse.error(
            name,
            summary="This advice could not be prepared right now. Please try again.",
            details={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                # Useful during the hackathon; strip before any public deployment.
                "traceback": traceback.format_exc(limit=5),
            },
        )


def run_all(aggregated: AggregatedData) -> list[ModuleResponse]:
    """Every registered module, in dashboard order."""
    return [run_module(name, aggregated) for name in MODULE_ORDER]
