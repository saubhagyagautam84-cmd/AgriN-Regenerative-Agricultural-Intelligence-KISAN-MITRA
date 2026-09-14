"""
End-to-end check of the backend.

    cd backend
    .venv\\Scripts\\python.exe smoke_test.py

Sections 1-6 (Part A) call the pipeline functions directly - no server
needed. Section 7+ (Part B) makes real HTTP requests against a RUNNING
backend (http://127.0.0.1:8001 by default, override with SMOKE_TEST_BASE_URL)
because /api/regenerate and /api/crop-health-check exercise things a direct
function call can't: FastAPI's routing/validation, multipart upload
handling, and cnn_health.py's actual subprocess bridge to the isolated
TensorFlow venv. Start the backend first (see README > Quick start), or run
this via ../verify.sh, which starts nothing itself but documents the
precondition.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models.schemas import FarmInput  # noqa: E402
from services import auth as auth_service  # noqa: E402
from services import data_loader  # noqa: E402
from services.aggregator import aggregate_as_module_response, aggregate_farm_data  # noqa: E402
from services.modules import run_all  # noqa: E402

BASE_URL = os.environ.get("SMOKE_TEST_BASE_URL", "http://127.0.0.1:8001")


def line(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def post_json(path: str, payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def http_request(method: str, path: str, *, headers: dict | None = None, body: dict | None = None) -> tuple[int, dict | list]:
    """GET/DELETE (and anything else post_json doesn't cover) with optional auth headers."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"Content-Type": "application/json"} if body is not None else {}
    request_headers.update(headers or {})
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else {}


def post_multipart_photo(path: str, image_path: Path, crop_name: str) -> tuple[int, dict]:
    boundary = "----smoke-test-boundary"
    image_bytes = image_path.read_bytes()
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="crop_name"\r\n\r\n'
            f"{crop_name}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="{image_path.name}"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode("utf-8")
        + image_bytes
        + f"\r\n--{boundary}--\r\n".encode("utf-8")
    )
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        # This call's cold-start is the CNN subprocess bridge spinning up an
        # isolated TensorFlow venv (cnn_health.py) - not a network call, and
        # its latency depends entirely on what else is competing for RAM/CPU
        # on the machine at the time (observed 15-30s+ on the 8GB laptop this
        # was built on). 30s was measured too tight under load; 90s gives
        # real headroom without masking an actual hang.
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def find_sample_photo(class_prefix: str = "Potato") -> Path | None:
    subset_dir = Path(__file__).resolve().parent / "cnn_training" / "subset_small"
    candidates = sorted(subset_dir.glob(f"{class_prefix}*/*.jpg")) + sorted(subset_dir.glob(f"{class_prefix}*/*.JPG"))
    if candidates:
        return candidates[0]
    # Fall back to any class if the requested one isn't present.
    any_candidates = sorted(subset_dir.glob("*/*.jpg")) + sorted(subset_dir.glob("*/*.JPG"))
    return any_candidates[0] if any_candidates else None


def main() -> int:
    line("1. DATASET LOAD REPORT")
    health = data_loader.data_health()  # same data GET /api/health/data returns

    soil = health["soil_health_card"]
    print(
        "soil_health_card.csv: in_file={rows_in_file} parsed={rows_parsed} "
        "valid={rows_valid} rejected={rows_rejected} parser_skipped={parser_skipped_lines}".format(**soil)
    )
    for rejected in soil["rejected"]:
        print("   REJECTED line {line}: {reason}".format(**rejected))
    if soil["parser_skipped_lines"]:
        print(f"   PARSER SKIPPED {soil['parser_skipped_lines']} line(s) with the wrong field count")

    crops = health["crop_reference"]
    print(
        "crop_reference.json:  in_file={crops_in_file} valid={crops_valid} "
        "rejected={crops_rejected} error={error}".format(**crops)
    )
    pins = health["pincode_lookup"]
    print(f"pincode_lookup.csv:   valid={pins['rows_valid']} error={pins['error']}")

    line("2. CROP DROPDOWN (GET /api/crops)")
    for option in data_loader.list_crops():
        print(f"   {option.crop_name:<14} {option.local_name or '':<10} {option.season}")

    line("3. AGGREGATE (POST /api/aggregate)")
    farm_input = FarmInput(
        farmer_name="Ramesh Kumar",
        pincode="141001",
        land_size=2.5,
        land_unit="acre",
        crop_name="gehu",  # deliberately a local alias, not "Wheat"
        sowing_date=datetime.date.today() - datetime.timedelta(days=40),
        irrigation_source="borewell",
        soil_test_available=True,
    )
    aggregated = aggregate_farm_data(farm_input)
    print(f"   request_id     : {aggregated.request_id}")
    print(f"   land           : {aggregated.land_size_hectare} ha")
    print(f"   days since sow : {aggregated.days_since_sowing}  -> stage '{aggregated.crop_stage_hint}'")
    print(f"   location       : {aggregated.location.village}, {aggregated.location.district}, {aggregated.location.state}")
    assert aggregated.soil is not None, "expected a soil match for PIN 141001"
    print(f"   soil match     : {aggregated.soil.match_level} ({aggregated.soil.records_averaged} sample/s), N={aggregated.soil.n_kg_per_ha} pH={aggregated.soil.ph}")
    assert aggregated.crop_reference is not None, "'gehu' should resolve to Wheat"
    print(f"   crop resolved  : 'gehu' -> {aggregated.crop_reference.crop_name}")
    assert aggregated.weather is not None
    print(f"   weather        : {aggregated.weather.rainfall_last_7d_mm} mm last 7d, ET0 {aggregated.weather.et0_mm_per_day} mm/day")
    print(f"   completeness   : {aggregated.completeness}")
    print(f"   data gaps      : {aggregated.data_gaps or 'none'}")
    for warning in aggregated.warnings:
        print(f"   WARNING        : {warning}")

    envelope = aggregate_as_module_response(aggregated)
    print(f"   envelope       : status={envelope.status} module={envelope.module_name}")

    # run_all() calls the exact same module functions these 5 routes call:
    # POST /api/soil-status, POST /api/irrigation-advice,
    # POST /api/crop-recommendation, POST /api/rotation-suggestion, and
    # POST /api/analyze (aggregate_as_module_response + run_all together).
    line("4. MODULES (the 4 /api/* endpoints)")
    for response in run_all(aggregated):
        print(f"\n   [{response.status.upper():<7}] {response.module_name}  confidence={response.confidence}")
        print(f"   summary: {response.summary}")
        for action in response.details.get("farmer_actions", [])[:3]:
            print(f"      - {action}")

    line("5. MISSING-DATA PATH (unknown PIN code + unknown crop)")
    sparse = FarmInput(
        pincode="999999",
        land_size=1,
        land_unit="hectare",
        crop_name="dragon fruit",
        sowing_date=datetime.date.today(),
        irrigation_source="rainfed",
    )
    sparse_aggregated = aggregate_farm_data(sparse)
    print(f"   completeness : {sparse_aggregated.completeness}")
    print(f"   data gaps    : {sparse_aggregated.data_gaps}")
    for response in run_all(sparse_aggregated):
        print(f"   [{response.status.upper():<7}] {response.module_name}: {response.summary}")
        assert response.status != "error" or response.module_name == "irrigation_advice"

    line("6. SAMPLE ModuleResponse JSON (the shared contract)")
    sample = run_all(aggregated)[1]
    payload = sample.model_dump(mode="json")
    payload["details"] = {
        key: payload["details"][key]
        for key in list(payload["details"])[:4]
    }
    payload["details"]["...."] = "(truncated for display)"
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    line("7. PART B - /api/regenerate (server must be running - see module docstring)")
    try:
        urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=5)
    except (urllib.error.URLError, ConnectionError) as exc:
        print(f"   SKIPPED - backend not reachable at {BASE_URL} ({exc}).")
        print("   Start it first: backend/.venv/Scripts/python.exe -m uvicorn main:app --port 8001")
        print("\nPart A checks passed; Part B skipped (no running server).\n")
        return 0

    def assert_regen_response(label: str, payload: dict) -> None:
        expected_keys = {
            "module_1_rotation",
            "module_2_soil_health",
            "module_3_fertilizer",
            "module_4_cover_cropping",
            "module_5_irrigation",
            "regeneration_score",
        }
        missing = expected_keys - payload.keys()
        assert not missing, f"{label}: missing keys {missing}"
        regen = payload["regeneration_score"]
        score = regen["score"]
        assert score is None or 0 <= score <= 100, f"{label}: regeneration_score.score {score} out of 0-100"
        confidence = regen["confidence"]
        assert confidence in (None, "High", "Estimated", "Low confidence — mostly regional averages"), (
            f"{label}: unexpected confidence {confidence!r}"
        )
        if score is not None:
            # Part C (backend/regeneration_score/) fields - present on every
            # non-null score, absent (null) only on the all-5-modules-failed path.
            for key in ("breakdown", "score_tone", "weakest_module", "improvement_tip"):
                assert regen.get(key) is not None, f"{label}: expected non-null '{key}' alongside a real score"
            assert regen["weakest_module"] in regen["breakdown"], f"{label}: weakest_module not one of the 5 breakdown entries"
        print(f"   [OK] {label}: score={score} confidence={confidence} weakest={regen.get('weakest_module')}")

    scenarios = {
        "full data (soil test provided)": {
            "pincode": "141001",
            "land_size": 2.5,
            "land_unit": "acre",
            "crop_name": "gehu",
            "crop_intent": "current",
            "sowing_date": str(datetime.date.today() - datetime.timedelta(days=40)),
            "irrigation_source": "borewell",
            "soil_test_available": True,
            "soil_test_n_kg_per_ha": 240,
            "soil_test_p_kg_per_ha": 15,
            "soil_test_k_kg_per_ha": 140,
            "soil_test_ph": 6.8,
            "soil_test_organic_carbon_pct": 0.6,
        },
        "missing soil-test fallback": {
            "pincode": "141001",
            "land_size": 1.0,
            "land_unit": "hectare",
            "crop_name": "Rice",
            "crop_intent": "current",
            "sowing_date": str(datetime.date.today() - datetime.timedelta(days=20)),
            "irrigation_source": "canal",
            "soil_test_available": False,
        },
        "missing-photo fallback (crop_health_score omitted)": {
            "pincode": "462001",
            "land_size": 3.0,
            "land_unit": "acre",
            "crop_name": "Soybean",
            "crop_intent": "current",
            "sowing_date": str(datetime.date.today() - datetime.timedelta(days=15)),
            "irrigation_source": "tubewell",
            "soil_test_available": False,
        },
        "rain-only water source special case": {
            "pincode": "141001",
            "land_size": 1.5,
            "land_unit": "acre",
            "crop_name": "Pearl Millet",
            "crop_intent": "current",
            "sowing_date": str(datetime.date.today() - datetime.timedelta(days=10)),
            "irrigation_source": "rainfed",
            "soil_test_available": False,
        },
        "unresolved PIN (no Soil Health Card on file at all)": {
            "pincode": "999999",
            "land_size": 1.0,
            "land_unit": "hectare",
            "crop_name": "Rice",
            "crop_intent": "current",
            "sowing_date": str(datetime.date.today() - datetime.timedelta(days=20)),
            "irrigation_source": "canal",
            "soil_test_available": False,
        },
    }
    for label, body in scenarios.items():
        status, payload = post_json("/api/regenerate", body)
        assert status == 200, f"{label}: expected HTTP 200, got {status} - {payload}"
        assert_regen_response(label, payload)

    # The unresolved-PIN scenario is the one genuinely missing soil data
    # (the other "missing soil-test" scenarios still resolve real Soil
    # Health Card records by PIN regardless of the checkbox) - confirm it
    # bottoms out at the Geographic Confidence Ladder's new sparse-data
    # label: PIN 999999 isn't in geo_reference.json at all, so BOTH chains
    # (resolve_soil_field and resolve_crop_suitability) fall all the way to
    # national_avg, proving confidence traces real data provenance rather
    # than the farmer's soil_test_available claim.
    unresolved_payload = post_json("/api/regenerate", scenarios["unresolved PIN (no Soil Health Card on file at all)"])[1]
    unresolved_confidence = unresolved_payload["regeneration_score"]["confidence"]
    assert unresolved_confidence == "Low confidence — mostly regional averages", (
        "unresolved PIN should degrade confidence to the sparse-data label "
        f"(no soil data anywhere to trace back to), got {unresolved_confidence!r}"
    )
    print("   [OK] unresolved PIN correctly degrades regeneration_score.confidence to the sparse-data label")

    missing_photo_payload = post_json("/api/regenerate", scenarios["missing-photo fallback (crop_health_score omitted)"])[1]
    m1_reasons = " ".join(
        r for entry in missing_photo_payload["module_1_rotation"]["details"].get("next_crop_suggestions", []) for r in entry.get("reasons", [])
    )
    assert "photo health check flagged stress" not in m1_reasons, (
        "omitting crop_health_score should assume baseline health (1.0) - M1 should not apply the stress bonus"
    )
    print("   [OK] missing-photo fallback correctly assumed baseline health (no stress bonus applied in M1)")

    line("8. PART B - /api/crop-health-check")
    sample_photo = find_sample_photo("Potato")
    if sample_photo is None:
        print("   SKIPPED - no sample photo found under backend/cnn_training/subset_small/")
        print("   (expected on a fresh clone before training data is fetched - see README)")
    else:
        status, payload = post_multipart_photo("/api/crop-health-check", sample_photo, "Potato")
        assert status == 200, f"crop-health-check: expected HTTP 200, got {status} - {payload}"
        for key in ("health_score", "label", "is_placeholder", "note"):
            assert key in payload, f"crop-health-check: missing key {key!r} in {payload}"
        assert 0.0 <= payload["health_score"] <= 1.0, f"health_score out of range: {payload['health_score']}"
        print(f"   [OK] supported crop (Potato, {sample_photo.name}) -> health_score={payload['health_score']} is_placeholder={payload['is_placeholder']}")

        # Unsupported-crop fallback: same photo, but claimed as a crop the
        # CNN was never trained on - must NOT return a confident guess.
        status, payload = post_multipart_photo("/api/crop-health-check", sample_photo, "Wheat")
        assert status == 200, f"crop-health-check (unsupported crop): expected HTTP 200, got {status} - {payload}"
        assert payload["is_placeholder"] is True, "unsupported crop should return is_placeholder=True, not a guessed classification"
        assert payload["label"] == "unsupported_crop", f"expected label='unsupported_crop', got {payload['label']!r}"
        print(f"   [OK] unsupported crop (Wheat) correctly returned label='unsupported_crop', is_placeholder=True")

    line("9. AUTH + FAMILY MEMBERS (real phone-OTP login, see services/auth.py)")

    # 9a. /api/auth/verify with a bogus Firebase ID token must never crash or
    #     silently "log someone in" - either 503 (FIREBASE_PROJECT_ID unset,
    #     the expected state on a fresh clone) or 401 (configured, token
    #     rejected). Never 200.
    status, payload = http_request("POST", "/api/auth/verify", body={"id_token": "not-a-real-token"})
    assert status in (401, 503), f"auth/verify with a bogus token should be 401 or 503, got {status} - {payload}"
    print(f"   [OK] /api/auth/verify with a bogus token correctly rejected (HTTP {status})")

    # 9b. Every family-members endpoint must require a session.
    status, payload = http_request("GET", "/api/family-members")
    assert status == 401, f"family-members without a session should be 401, got {status}"
    status, payload = http_request("POST", "/api/family-members", body={"name": "X"})
    assert status == 401, f"adding a family member without a session should be 401, got {status}"
    print("   [OK] /api/family-members correctly requires a session (401 without one)")

    # 9c. The authenticated path, exercised through the real HTTP layer (not
    #     just the service functions) by minting a session the same way a
    #     real Firebase-verified login would, bypassing only the external
    #     SMS step this environment has no live Firebase project for.
    test_user = auth_service.VerifiedFirebaseUser(uid="smoke-test-uid", phone="+910000000000")
    session_token = auth_service.upsert_user_and_create_session(test_user)
    auth_headers = {"Authorization": f"Bearer {session_token}"}
    try:
        status, payload = http_request("GET", "/api/auth/me", headers=auth_headers)
        assert status == 200 and payload["phone"] == test_user.phone, f"auth/me: expected phone {test_user.phone!r}, got {payload}"

        status, created = http_request("POST", "/api/family-members", headers=auth_headers, body={"name": "Smoke Test Member", "phone": "9000000000"})
        assert status == 200, f"add family member: expected HTTP 200, got {status} - {created}"
        assert created["name"] == "Smoke Test Member"

        status, listed = http_request("GET", "/api/family-members", headers=auth_headers)
        assert status == 200 and any(m["id"] == created["id"] for m in listed), "newly added family member should appear in the list"

        # DELETE /api/family-members/{member_id}
        status, _ = http_request("DELETE", f"/api/family-members/{created['id']}", headers=auth_headers)
        assert status == 204, f"remove family member: expected HTTP 204, got {status}"

        status, listed_after = http_request("GET", "/api/family-members", headers=auth_headers)
        assert not any(m["id"] == created["id"] for m in listed_after), "removed family member should no longer appear in the list"
        print("   [OK] authenticated session: /api/auth/me + full add/list/remove family-member cycle")
    finally:
        status, _ = http_request("POST", "/api/auth/logout", headers=auth_headers)
        assert status == 204, f"auth/logout: expected HTTP 204, got {status}"
        status, _ = http_request("GET", "/api/auth/me", headers=auth_headers)
        assert status == 401, "a logged-out session must stop authenticating immediately"
        print("   [OK] /api/auth/logout immediately invalidates the session")

    line("10. REAL SEASON HISTORY + PEER COMPARISON + FARMER-CONTRIBUTED SOIL LOOP")

    # 10a. history.source: "simulated" (M2's projection) for a farm_id's
    # first-ever submission, "real" (services/score_history.py's actual
    # stored snapshots) from the second submission on - regardless of how
    # many times this whole smoke test has been re-run before (the DB
    # persists across runs), the SECOND of two back-to-back calls for the
    # SAME farm_id must always see at least one real prior point.
    history_probe_body = {
        "pincode": "226001", "land_size": 1.0, "land_unit": "acre", "crop_name": "smoke-test-history-crop",
        "crop_intent": "current", "sowing_date": str(datetime.date.today() - datetime.timedelta(days=30)),
        "irrigation_source": "canal", "soil_test_available": False,
    }
    post_json("/api/regenerate", history_probe_body)  # first call - establishes a prior point, result not asserted
    _, second_payload = post_json("/api/regenerate", history_probe_body)
    second_history = second_payload["regeneration_score"]["history"]
    assert second_history is not None and second_history["source"] == "real", (
        f"a farm_id's second submission must see real stored history, got {second_history!r}"
    )
    assert len(second_history["history"]) >= 2, "real history must include at least the prior point plus the current one"
    print(f"   [OK] history.source is 'real' from the 2nd submission on (trend={second_history['trend']!r})")

    # 10b. Peer comparison: submit enough DISTINCT farm_ids (different crop
    # names) in one district to cross peer_comparison.py's MIN_PEERS
    # threshold, then confirm the next submission in that district sees a
    # real, structurally sound comparison - never a fabricated one below
    # the threshold.
    peer_district_pincode = "250001"  # Meerut - not used by any earlier scenario in this file
    for i in range(3):
        post_json("/api/regenerate", {
            "pincode": peer_district_pincode, "land_size": 1.0, "land_unit": "acre",
            "crop_name": f"smoke-test-peer-crop-{i}", "crop_intent": "current",
            "sowing_date": str(datetime.date.today() - datetime.timedelta(days=30)),
            "irrigation_source": "canal", "soil_test_available": False,
        })
    _, peer_payload = post_json("/api/regenerate", {
        "pincode": peer_district_pincode, "land_size": 1.0, "land_unit": "acre",
        "crop_name": "smoke-test-peer-crop-final", "crop_intent": "current",
        "sowing_date": str(datetime.date.today() - datetime.timedelta(days=30)),
        "irrigation_source": "canal", "soil_test_available": False,
    })
    peer_comparison = peer_payload["regeneration_score"]["peer_comparison"]
    assert peer_comparison is not None, "after 3+ distinct nearby submissions, peer_comparison must no longer be null"
    assert peer_comparison["peer_count"] >= 3
    assert peer_comparison["scope"] == "district" and peer_comparison["label"]
    print(f"   [OK] peer_comparison populates once enough real nearby submissions exist ({peer_comparison['summary']})")

    # 10c. Farmer-contributed soil data loop: a soil-test submission with a
    # practically-unique reading (so dedup never masks it, run after run)
    # must increase the district's farmer_submitted_count by exactly 1, and
    # an EXACT resubmission of the same reading must not increase it again
    # - see services/farmer_soil_observations.py's content-hash dedupe.
    unique_marker = round(50 + (datetime.datetime.now().timestamp() % 100), 3)
    contribution_district = "Amritsar"
    status, before = http_request("GET", f"/api/soil-observations/stats?district={contribution_district}")
    assert status == 200
    contribution_body = {
        "pincode": "143001", "land_size": 1.0, "land_unit": "acre", "crop_name": "smoke-test-contribution-crop",
        "crop_intent": "current", "sowing_date": str(datetime.date.today() - datetime.timedelta(days=30)),
        "irrigation_source": "canal", "soil_test_available": True,
        "soil_test_n_kg_per_ha": unique_marker, "soil_test_p_kg_per_ha": 12, "soil_test_k_kg_per_ha": 110,
        "soil_test_ph": 6.7, "soil_test_organic_carbon_pct": 0.5,
    }
    post_json("/api/regenerate", contribution_body)
    status, after_first = http_request("GET", f"/api/soil-observations/stats?district={contribution_district}")
    assert after_first["farmer_submitted_count"] == before["farmer_submitted_count"] + 1, (
        f"a new soil-test submission should add exactly 1 farmer-contributed observation, "
        f"before={before['farmer_submitted_count']} after={after_first['farmer_submitted_count']}"
    )
    post_json("/api/regenerate", contribution_body)  # exact resubmission
    status, after_second = http_request("GET", f"/api/soil-observations/stats?district={contribution_district}")
    assert after_second["farmer_submitted_count"] == after_first["farmer_submitted_count"], (
        "an EXACT resubmission of the same reading must be deduped, not counted again"
    )
    print(f"   [OK] farmer-contributed soil data loop: +1 on a new reading, deduped on an exact repeat ({contribution_district}: {after_second['farmer_submitted_count']} total)")

    line("11. SMS/IVR FALLBACK CHANNEL (see services/telephony.py)")

    status, payload = http_request("POST", "/api/sms/regenerate", body={"from_phone": "+919876500001", "body": "141001 WHEAT 20 BOREWELL"})
    assert status == 200, f"sms/regenerate: expected HTTP 200, got {status} - {payload}"
    assert payload["understood"] is True
    assert "Regen score" in payload["reply_text"], f"expected a compact regen-score reply, got {payload['reply_text']!r}"
    print(f"   [OK] SMS command (no soil test) understood: {payload['reply_text']!r}")

    status, payload = http_request("POST", "/api/sms/regenerate", body={"from_phone": "+919876500001", "body": "141001 WHEAT 20 BOREWELL 240 15 140 6.8 0.6"})
    assert status == 200 and payload["understood"] is True
    assert "Regen score" in payload["reply_text"]
    print(f"   [OK] SMS command (with soil test) understood: {payload['reply_text']!r}")

    status, payload = http_request("POST", "/api/sms/regenerate", body={"from_phone": "+919876500001", "body": "this is not a real command at all"})
    assert status == 200, f"an unparseable SMS must still reply 200 with a help message, never a 500, got {status}"
    assert payload["understood"] is False
    assert "PIN CROP DAYS IRRIGATION" in payload["reply_text"]
    print("   [OK] unparseable SMS command (wrong token count) replies with the format hint instead of erroring")

    status, payload = http_request("POST", "/api/sms/regenerate", body={"from_phone": "+919876500001", "body": "notapin WHEAT 20 BOREWELL"})
    assert status == 200
    assert payload["understood"] is False
    assert "PIN code" in payload["reply_text"], f"expected a PIN-specific error, got {payload['reply_text']!r}"
    print("   [OK] a 4-token command with an invalid PIN replies with a specific PIN error, not a crash")

    print("\nAll checks passed (Part A + Part B).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
