"""
FastAPI entry point.

Run from the `backend/` folder:
    uvicorn main:app --reload --port 8000

Interactive API docs once it is up:
    http://127.0.0.1:8000/docs

Endpoint map
------------
GET  /api/health              service liveness
GET  /api/health/data         dataset load report (rejected rows etc.)
GET  /api/crops               crop list for the form dropdown
POST /api/aggregate           STEP 3 - merged farm data
POST /api/soil-status         STEP 4 - module 1
POST /api/irrigation-advice   STEP 4 - module 2
POST /api/crop-recommendation STEP 4 - module 3
POST /api/rotation-suggestion STEP 4 - module 4
POST /api/analyze             aggregate + all 4 modules in one round trip

Every POST above takes the same body (FarmInput) and every one of them
returns the same envelope (ModuleResponse). That uniformity is the whole
point of the skeleton.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow both `uvicorn main:app` (from backend/) and `uvicorn backend.main:app`
# (from the repo root) to resolve the `models` / `services` packages.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, File, Request, UploadFile  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from models.schemas import (  # noqa: E402
    AnalyzeResponse,
    CropHealthCheckResponse,
    CropOption,
    FarmInput,
    ModuleResponse,
    RegenAnalyzeResponse,
    now_iso,
)
from services import data_loader  # noqa: E402
from services.aggregator import aggregate_as_module_response, aggregate_farm_data  # noqa: E402
from services.modules import MODULE_ORDER, run_all, run_module  # noqa: E402
from services.regen import run_regen_pipeline  # noqa: E402
from services.regen.cnn_health import predict_crop_health  # noqa: E402

app = FastAPI(
    title="Farm Monitoring API",
    version="0.1.0",
    description=(
        "Part A skeleton: farmer input -> aggregated farm data -> 4 advisory modules. "
        "All advisory output is currently rule-based/dummy and is marked "
        "`details.is_dummy_data = true`."
    ),
)

# The Next.js dev server. Override with ALLOWED_ORIGINS="http://a,http://b".
DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Validation errors -> a shape the form can render field-by-field
# --------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", []) if part != "body"]
        errors.append(
            {
                "field": ".".join(location) or "body",
                "message": error.get("msg", "Invalid value"),
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "Some details need fixing before we can continue.",
            "errors": errors,
            "timestamp": now_iso(),
        },
    )


# --------------------------------------------------------------------------
# Health + reference
# --------------------------------------------------------------------------


@app.get("/", tags=["health"], summary="Service info")
def root() -> dict:
    return {
        "service": "Farm Monitoring API",
        "version": app.version,
        "docs": "/docs",
        "modules": MODULE_ORDER,
    }


@app.get("/api/health", tags=["health"], summary="Liveness")
def health() -> dict:
    return {"status": "ok", "timestamp": now_iso()}


@app.get("/api/health/data", tags=["health"], summary="Dataset load report - rows read, rows rejected, why")
def health_data() -> dict:
    """
    How the datasets loaded: rows read, rows rejected and why.

    The shipped soil CSV contains two intentionally broken rows so the team
    can see this endpoint doing its job. See README > Seed data.
    """
    return data_loader.data_health()


@app.get("/api/crops", response_model=list[CropOption], tags=["reference"], summary="Crop list for the form dropdown")
def crops() -> list[CropOption]:
    """Feeds the crop dropdown in the farmer form."""
    return data_loader.list_crops()


# --------------------------------------------------------------------------
# STEP 3 - the aggregator
# --------------------------------------------------------------------------


@app.post(
    "/api/aggregate",
    response_model=ModuleResponse,
    tags=["aggregate"],
    summary="STEP 3 - merged farm object in `details`",
)
def aggregate(farm_input: FarmInput) -> ModuleResponse:
    """
    Merge farmer input with soil card + weather + crop reference.

    `details` holds the full AggregatedData object - the same object every
    module receives internally.
    """
    aggregated = aggregate_farm_data(farm_input)
    return aggregate_as_module_response(aggregated)


# --------------------------------------------------------------------------
# STEP 4 - one endpoint per module, all returning ModuleResponse
# --------------------------------------------------------------------------


@app.post("/api/soil-status", response_model=ModuleResponse, tags=["modules"], summary="Module 1 - soil status")
def soil_status_endpoint(farm_input: FarmInput) -> ModuleResponse:
    return run_module("soil_status", aggregate_farm_data(farm_input))


@app.post(
    "/api/irrigation-advice", response_model=ModuleResponse, tags=["modules"], summary="Module 2 - irrigation advice"
)
def irrigation_endpoint(farm_input: FarmInput) -> ModuleResponse:
    return run_module("irrigation_advice", aggregate_farm_data(farm_input))


@app.post(
    "/api/crop-recommendation",
    response_model=ModuleResponse,
    tags=["modules"],
    summary="Module 3 - crop recommendation",
)
def crop_recommendation_endpoint(farm_input: FarmInput) -> ModuleResponse:
    return run_module("crop_recommendation", aggregate_farm_data(farm_input))


@app.post(
    "/api/rotation-suggestion", response_model=ModuleResponse, tags=["modules"], summary="Module 4 - rotation suggestion"
)
def rotation_endpoint(farm_input: FarmInput) -> ModuleResponse:
    return run_module("rotation_suggestion", aggregate_farm_data(farm_input))


@app.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
    tags=["modules"],
    summary="Aggregate + all 4 Part A modules in one round trip",
)
def analyze(farm_input: FarmInput) -> AnalyzeResponse:
    """
    Everything in one call: aggregate once, then fan out to all modules.

    Cheaper than the five separate calls the dashboard makes by default -
    switch `USE_COMBINED_ENDPOINT` in frontend/lib/api.ts to use this.
    """
    aggregated = aggregate_farm_data(farm_input)
    return AnalyzeResponse(
        aggregate=aggregate_as_module_response(aggregated),
        modules=run_all(aggregated),
    )


# --------------------------------------------------------------------------
# PART B - the Regenerative Intelligence Engine
# --------------------------------------------------------------------------


@app.post(
    "/api/crop-health-check",
    response_model=CropHealthCheckResponse,
    tags=["regen"],
    summary="STEP 4 - CNN crop photo health check (multipart upload)",
)
async def crop_health_check(photo: UploadFile = File(...)) -> CropHealthCheckResponse:
    """
    Runs the trained MobileNetV2 model (see backend/cnn_training/) via a
    subprocess bridge (services/regen/cnn_health.py) - only recognises
    Corn (maize), Potato and Soybean, the 3 of Kisan Sathi's 18 crops that
    exist in the PlantVillage training data. Any other crop, or if the
    model files aren't present, falls back to a baseline placeholder
    result rather than a wrong prediction - never blocks the form.

    The frontend calls this first (only if a photo was taken) and carries
    the resulting `health_score` into FarmInput.crop_health_score before
    submitting the rest of the form to /api/regenerate.
    """
    image_bytes = await photo.read()
    result = predict_crop_health(image_bytes)
    return CropHealthCheckResponse(
        health_score=result.score,
        label=result.label,
        is_placeholder=result.is_placeholder,
        note=result.note,
    )


@app.post(
    "/api/regenerate",
    response_model=RegenAnalyzeResponse,
    tags=["regen"],
    summary="Part B - Feature Resolver + 5 modules + Regeneration Score Engine",
)
def regenerate(farm_input: FarmInput) -> RegenAnalyzeResponse:
    """
    Part B's single entry point: Feature Resolver -> 5 modules (with the
    M1<->M2<->M4 cross-dependencies preserved) -> Regeneration Score Engine.
    Returns the exact Output Contract from the Part B spec.
    """
    aggregated = aggregate_farm_data(farm_input)
    return run_regen_pipeline(farm_input, aggregated)
