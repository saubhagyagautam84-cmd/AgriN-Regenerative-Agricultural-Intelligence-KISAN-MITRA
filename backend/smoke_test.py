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
        with urllib.request.urlopen(request, timeout=30) as response:
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
        assert confidence in (None, "High", "Estimated"), f"{label}: unexpected confidence {confidence!r}"
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
    # actually produces "Estimated", proving confidence traces real data
    # provenance rather than the farmer's soil_test_available claim.
    unresolved_payload = post_json("/api/regenerate", scenarios["unresolved PIN (no Soil Health Card on file at all)"])[1]
    unresolved_confidence = unresolved_payload["regeneration_score"]["confidence"]
    assert unresolved_confidence == "Estimated", (
        f"unresolved PIN should degrade confidence to 'Estimated' (no soil data anywhere to trace back to), got {unresolved_confidence!r}"
    )
    print("   [OK] unresolved PIN correctly degrades regeneration_score.confidence to 'Estimated'")

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

    print("\nAll checks passed (Part A + Part B).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
