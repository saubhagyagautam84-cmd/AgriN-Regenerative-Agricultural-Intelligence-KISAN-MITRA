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
POST /api/regenerate          Part B - Feature Resolver + 5 modules + Regeneration Score Engine
GET  /api/soil-observations/stats   farmer-contributed soil data loop - counts by district
POST /api/sms/regenerate      SMS/IVR fallback channel - see services/telephony.py

Every POST above takes the same body (FarmInput) and every one of them
returns the same envelope (ModuleResponse). That uniformity is the whole
point of the skeleton.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Allow both `uvicorn main:app` (from backend/) and `uvicorn backend.main:app`
# (from the repo root) to resolve the `models` / `services` packages.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from models.schemas import (  # noqa: E402
    AnalyzeResponse,
    AuthMeResponse,
    AuthVerifyRequest,
    AuthVerifyResponse,
    CropHealthCheckResponse,
    CropOption,
    FamilyMemberIn,
    FamilyMemberOut,
    FarmInput,
    ModuleResponse,
    RegenAnalyzeResponse,
    SmsInboundRequest,
    SmsInboundResponse,
    SoilObservationStats,
    now_iso,
)
from services import auth as auth_service  # noqa: E402
from services import data_loader  # noqa: E402
from services import farmer_soil_observations  # noqa: E402
from services import score_history  # noqa: E402
from services import telephony  # noqa: E402
from services.aggregator import aggregate_as_module_response, aggregate_farm_data  # noqa: E402
from services.modules import MODULE_ORDER, run_all, run_module  # noqa: E402
from services.regen import run_regen_pipeline  # noqa: E402
from services.regen.cnn_health import predict_crop_health  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    auth_service.init_db()
    score_history.init_db()
    farmer_soil_observations.init_db()
    yield


app = FastAPI(
    title="Farm Monitoring API",
    version="0.1.0",
    description=(
        "Part A skeleton: farmer input -> aggregated farm data -> 4 advisory modules. "
        "All advisory output is currently rule-based/dummy and is marked "
        "`details.is_dummy_data = true`."
    ),
    lifespan=lifespan,
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
async def crop_health_check(
    photo: UploadFile = File(...),
    crop_name: str = Form(...),
) -> CropHealthCheckResponse:
    """
    Runs the trained MobileNetV2 model (see backend/cnn_training/) via a
    subprocess bridge (services/regen/cnn_health.py) - only recognises
    Corn (maize), Potato and Soybean, the 3 of Kisan Mitra's 18 crops that
    exist in the PlantVillage training data. `crop_name` is required so an
    unsupported crop's photo is honestly reported (`label:
    "unsupported_crop"`) instead of silently returning a wrong prediction.
    If the model files aren't present, falls back to the same baseline
    placeholder - never blocks the form either way.

    The frontend calls this first (only if a photo was taken) and carries
    the resulting `health_score` into FarmInput.crop_health_score before
    submitting the rest of the form to /api/regenerate.
    """
    image_bytes = await photo.read()
    result = predict_crop_health(image_bytes, crop_name)
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


@app.get(
    "/api/soil-observations/stats",
    response_model=SoilObservationStats,
    tags=["regen"],
    summary="Farmer-contributed soil data loop - how many real readings exist for a district",
)
def soil_observations_stats(district: Optional[str] = None) -> SoilObservationStats:
    """
    Transparency endpoint for the farmer-contributed soil data loop (see
    services/farmer_soil_observations.py): every soil-test submission a
    farmer makes through the normal wizard densifies their district's
    average for OTHER nearby farmers. This lets the frontend show that
    honestly instead of just asserting it happens invisibly.
    """
    farmer_count = farmer_soil_observations.count_observations(district=district)
    official_records, _ = data_loader.load_soil_records()
    official_count = sum(
        1 for r in official_records if district is None or (r.district or "").strip().lower() == district.strip().lower()
    )
    return SoilObservationStats(
        district=district, farmer_submitted_count=farmer_count, official_soil_health_card_count=official_count
    )


@app.post(
    "/api/sms/regenerate",
    response_model=SmsInboundResponse,
    tags=["regen"],
    summary="SMS/IVR fallback channel - a gateway webhook posts an inbound text here, gets back a reply to send",
)
def sms_regenerate(body: SmsInboundRequest) -> SmsInboundResponse:
    """
    The fallback channel for farmers without a smartphone or data connection
    - see services/telephony.py for the command format and the
    provider-agnostic send_sms() interface (a real SMS gateway's inbound
    webhook posts here in production; TELEPHONY_PROVIDER=console's local
    simulator stands in until a real provider account exists).
    """
    parsed = telephony.parse_sms_command(body.body)
    if isinstance(parsed, str):
        telephony.send_sms(body.from_phone, parsed)
        return SmsInboundResponse(reply_text=parsed, understood=False)

    try:
        farm_input = FarmInput(
            pincode=parsed.pincode,
            land_size=1.0,
            land_unit="acre",
            crop_name=parsed.crop_name,
            crop_intent="current",
            sowing_date=parsed.sowing_date,
            irrigation_source=parsed.irrigation_source,
            soil_test_available=parsed.soil_test_available,
            soil_test_n_kg_per_ha=parsed.soil_test_n_kg_per_ha,
            soil_test_p_kg_per_ha=parsed.soil_test_p_kg_per_ha,
            soil_test_k_kg_per_ha=parsed.soil_test_k_kg_per_ha,
            soil_test_ph=parsed.soil_test_ph,
            soil_test_organic_carbon_pct=parsed.soil_test_organic_carbon_pct,
        )
    except Exception as exc:  # noqa: BLE001 - a bad value must reply with SMS text, never a 500
        reply = f"Could not use those values: {str(exc).splitlines()[0]}"
        telephony.send_sms(body.from_phone, reply)
        return SmsInboundResponse(reply_text=reply, understood=False)

    aggregated = aggregate_farm_data(farm_input)
    result = run_regen_pipeline(farm_input, aggregated)
    regen = result.regeneration_score
    reply = telephony.format_sms_reply(regen.score, regen.confidence, regen.weakest_module, regen.improvement_tip)
    telephony.send_sms(body.from_phone, reply)
    return SmsInboundResponse(reply_text=reply, understood=True)


# --------------------------------------------------------------------------
# Auth (real phone-OTP login) + family members - see services/auth.py
# --------------------------------------------------------------------------


def require_session_user(
    authorization: str | None = Header(default=None),
) -> auth_service.SessionUser:
    """FastAPI dependency: every family-members endpoint needs a valid session."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not logged in.")
    token = authorization.removeprefix("Bearer ").strip()
    user = auth_service.get_session_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid - please log in again.")
    return user


@app.post(
    "/api/auth/verify",
    response_model=AuthVerifyResponse,
    tags=["auth"],
    summary="Exchange a Firebase Phone Auth ID token for this app's session token",
)
def auth_verify(body: AuthVerifyRequest) -> AuthVerifyResponse:
    try:
        firebase_user = auth_service.verify_firebase_id_token(body.id_token)
    except auth_service.AuthNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except auth_service.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    session_token = auth_service.upsert_user_and_create_session(firebase_user)
    return AuthVerifyResponse(session_token=session_token, phone=firebase_user.phone)


@app.get("/api/auth/me", response_model=AuthMeResponse, tags=["auth"], summary="Whoami - resolves a session token to its logged-in phone number")
def auth_me(user: auth_service.SessionUser = Depends(require_session_user)) -> AuthMeResponse:
    return AuthMeResponse(phone=user.phone)


@app.post("/api/auth/logout", tags=["auth"], status_code=204, summary="Invalidate the current session token")
def auth_logout(authorization: str | None = Header(default=None)) -> None:
    if authorization and authorization.startswith("Bearer "):
        auth_service.delete_session(authorization.removeprefix("Bearer ").strip())


@app.get("/api/family-members", response_model=list[FamilyMemberOut], tags=["family"], summary="List the logged-in farmer's family members")
def get_family_members(
    user: auth_service.SessionUser = Depends(require_session_user),
) -> list[FamilyMemberOut]:
    rows = auth_service.list_family_members(user.user_id)
    return [FamilyMemberOut(**dict(row)) for row in rows]


@app.post("/api/family-members", response_model=FamilyMemberOut, tags=["family"], summary="Add a family member to the logged-in farmer's account")
def post_family_member(
    body: FamilyMemberIn,
    user: auth_service.SessionUser = Depends(require_session_user),
) -> FamilyMemberOut:
    row = auth_service.add_family_member(user.user_id, body.name, body.phone)
    return FamilyMemberOut(**dict(row))


@app.delete("/api/family-members/{member_id}", tags=["family"], status_code=204, summary="Remove a family member from the logged-in farmer's account")
def delete_family_member(
    member_id: int,
    user: auth_service.SessionUser = Depends(require_session_user),
) -> None:
    found = auth_service.remove_family_member(user.user_id, member_id)
    if not found:
        raise HTTPException(status_code=404, detail="Family member not found.")
