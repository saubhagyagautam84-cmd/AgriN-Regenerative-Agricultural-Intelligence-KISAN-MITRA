"""
STEP 5 - edge case tests, one per case, against mocked module-output sets.

Run directly (no pytest dependency needed, matching this project's existing
smoke_test.py style):

    backend/.venv/Scripts/python.exe regeneration_score/test_edge_cases.py
"""

from __future__ import annotations

from regeneration_score.dynamic_weights import get_dynamic_weights
from regeneration_score.score_engine import compute_regeneration_score, STATIC_WEIGHTS
from services.regen.geo_resolvers import resolve_soil_field, resolve_crop_suitability


def mock_module(raw_score: float, confidence_source: str = "observed") -> dict:
    return {"raw_score": raw_score, "confidence_source": confidence_source}


def test_all_modules_missing() -> None:
    """Case: every module failed. Must return null score + the exact message, never a fabricated number."""
    all_missing = {name: None for name in STATIC_WEIGHTS}
    result = compute_regeneration_score(all_missing)

    assert result["regeneration_score"] is None, "score must be null when all modules are missing"
    assert result["confidence_level"] is None
    assert result["breakdown"] is None
    assert result["message"] == "Insufficient data - please complete soil test"
    print("[PASS] test_all_modules_missing")


def test_one_module_missing_still_scores() -> None:
    """Case: only ONE module failed (per the confirmed answer: not all-5, so this must still produce a real score)."""
    modules = {
        "M1_rotation": mock_module(78),
        "M2_soil_carbon": mock_module(65),
        "M3_fertilizer": None,  # this one failed
        "M4_cover_crop": mock_module(60),
        "M5_irrigation": mock_module(70),
    }
    result = compute_regeneration_score(modules)

    assert result["regeneration_score"] is not None, "one missing module must not null out the whole score"
    assert isinstance(result["regeneration_score"], float)
    assert 0 <= result["regeneration_score"] <= 100
    print(f"[PASS] test_one_module_missing_still_scores (score={result['regeneration_score']})")


def test_extremely_high_score_tone() -> None:
    """Case: 95+ score. Must say 'excellent, minor room for improvement', never 'perfect'."""
    all_excellent = {name: mock_module(99, "observed") for name in STATIC_WEIGHTS}
    result = compute_regeneration_score(all_excellent)

    assert result["regeneration_score"] >= 95, f"test setup should produce 95+, got {result['regeneration_score']}"
    assert "perfect" not in result["score_tone"].lower(), "must never claim perfection"
    assert "excellent" in result["score_tone"].lower()
    assert "minor room for improvement" in result["score_tone"].lower()
    print(f"[PASS] test_extremely_high_score_tone (score={result['regeneration_score']}, tone={result['score_tone']!r})")


def test_conflicting_modules_surfaced() -> None:
    """Case: M3 great, M2 terrible. The conflict must be visible in breakdown, not hidden by averaging."""
    conflicting = {
        "M1_rotation": mock_module(70),
        "M2_soil_carbon": mock_module(10, "observed"),  # terrible
        "M3_fertilizer": mock_module(95, "observed"),  # great
        "M4_cover_crop": mock_module(65),
        "M5_irrigation": mock_module(60),
    }
    result = compute_regeneration_score(conflicting)

    assert "_conflicts" in result["breakdown"], "a large M2-vs-M3 gap must be surfaced explicitly in breakdown"
    conflict_text = " ".join(result["breakdown"]["_conflicts"])
    assert "M2_soil_carbon" in conflict_text and "M3_fertilizer" in conflict_text
    # The plain weighted average would have quietly smoothed this over - prove it did NOT get hidden:
    print(f"[PASS] test_conflicting_modules_surfaced (regen_score={result['regeneration_score']}, conflicts={result['breakdown']['_conflicts']})")


def test_weights_always_sum_to_one() -> None:
    """Not explicitly one of the 3 cases in the table, but the spec calls this an 'easy silent bug' - test it here too."""
    try:
        compute_regeneration_score(
            {name: mock_module(50) for name in STATIC_WEIGHTS},
            weights={"M1_rotation": 0.20, "M2_soil_carbon": 0.25, "M3_fertilizer": 0.25, "M4_cover_crop": 0.15, "M5_irrigation": 0.10},  # sums to 0.95
        )
        raise AssertionError("expected ValueError for weights not summing to 1.0")
    except ValueError as exc:
        assert "sum to 1.0" in str(exc)
        print("[PASS] test_weights_always_sum_to_one (correctly rejected 0.95 total)")


def test_dynamic_weights_always_sum_to_one() -> None:
    """Step 6's own easy-silent-bug warning - test every water_source x has_soil_test combination."""
    for water_source in ("rainfed", "canal", "borewell", "tubewell", "tank_pond", "drip_sprinkler", "other"):
        for has_soil_test in (True, False):
            weights = get_dynamic_weights(water_source, has_soil_test)
            total = round(sum(weights.values()), 6)
            assert total == 1.0, f"dynamic weights for water_source={water_source!r}, has_soil_test={has_soil_test} summed to {total}, not 1.0"
    print("[PASS] test_dynamic_weights_always_sum_to_one (all 14 combinations)")


def test_improvement_tip_never_negative_for_high_raw_score() -> None:
    """
    Regression test: a module can be "weakest" purely because of low
    CONFIDENCE even when its raw_score is already excellent. Naively
    simulating a bump toward GOOD_TARGET_SCORE in that case would LOWER the
    simulated score, producing a nonsensical "could raise your score by
    ~-3 points". Found via manual audit, fixed by branching the simulation
    on confidence instead of raw_score when raw_score is already high.
    """
    modules = {
        "M1_rotation": mock_module(95, "observed"),
        "M2_soil_carbon": mock_module(95, "observed"),
        "M3_fertilizer": mock_module(95, "observed"),
        "M4_cover_crop": mock_module(95, "national_avg"),  # weakest by confidence, not by raw performance
        "M5_irrigation": mock_module(95, "observed"),
    }
    result = compute_regeneration_score(modules)

    assert result["weakest_module"] == "M4_cover_crop"
    assert "~-" not in result["improvement_tip"], f"improvement_tip must never show a negative delta: {result['improvement_tip']!r}"
    print(f"[PASS] test_improvement_tip_never_negative_for_high_raw_score (tip={result['improvement_tip']!r})")


def test_soil_and_crop_suitability_diverge_for_same_pin() -> None:
    """
    Geographic Confidence Ladder - the core behavior the two-chain design
    exists to enable: soil and crop-suitability confidence must be able to
    land on DIFFERENT rungs for the identical PIN code, because they
    degrade through different geography (soil skips the zone level
    entirely; crop suitability starts there).

    PIN 302001 (Jaipur) is real, already-existing test data: its only Soil
    Health Card row has a malformed extra column and is silently dropped by
    the CSV parser (confirmed: 0 valid Jaipur/Rajasthan records anywhere),
    while geo_reference.json still resolves it to a real agro-climatic
    zone. So soil correctly bottoms out at the ladder's floor while crop
    suitability sits comfortably at its normal starting rung.
    """
    soil = resolve_soil_field("302001", "ph", None)
    crop = resolve_crop_suitability("302001")

    assert soil.confidence_level == "national_avg", f"expected soil to fall through to national_avg, got {soil.confidence_level!r}"
    assert crop.confidence_level == "zone_baseline", f"expected crop suitability to sit at zone_baseline, got {crop.confidence_level!r}"
    assert soil.confidence_level != crop.confidence_level
    print(
        f"[PASS] test_soil_and_crop_suitability_diverge_for_same_pin "
        f"(soil={soil.confidence_level!r}, crop={crop.confidence_level!r})"
    )


def test_soil_resolution_skips_to_state_when_district_missing() -> None:
    """
    Each fallback step must actually CHECK data availability, not assume
    the next level down exists. PIN 147001 (Patiala, Punjab) has zero Soil
    Health Card rows for its own district (deliberately - see
    geo_reference.json's note on that entry) but Punjab as a whole does
    (Ludhiana + Amritsar). Resolution must land on state_avg, not error and
    not silently drop all the way to national_avg past a state average
    that was actually available.
    """
    resolved = resolve_soil_field("147001", "ph", None)
    assert resolved.confidence_level == "state_avg", f"expected state_avg (district has no data, state does), got {resolved.confidence_level!r}"
    assert resolved.value is not None
    print(f"[PASS] test_soil_resolution_skips_to_state_when_district_missing (level={resolved.confidence_level!r}, detail={resolved.detail!r})")


def test_farmer_own_value_always_wins() -> None:
    """The farmer's own entered value must outrank even a perfect block-level match."""
    resolved = resolve_soil_field("141001", "ph", 7.2)
    assert resolved.confidence_level == "observed"
    assert resolved.value == 7.2
    print("[PASS] test_farmer_own_value_always_wins")


def test_sparse_data_triggers_low_confidence_label() -> None:
    """
    A farmer profile with real geographic context but no real local data
    anywhere (equivalent to the spec's farmer_011_all_data_missing_insufficient
    sparse-data profile) must reach the NEW third label - not silently fall
    back to "Estimated" for every non-High case, which would hide just how
    thin the underlying data actually is.
    """
    sparse = {name: mock_module(55, "national_avg") for name in STATIC_WEIGHTS}
    result = compute_regeneration_score(sparse)

    assert result["confidence_level"] == "Low confidence — mostly regional averages", (
        f"expected the new sparse-data label, got {result['confidence_level']!r}"
    )
    print(f"[PASS] test_sparse_data_triggers_low_confidence_label (confidence_level={result['confidence_level']!r})")


def test_confidence_breakdown_carries_per_module_explanation() -> None:
    """STEP 6: the dashboard needs a level + a human explanation per module, not just a bare tier name."""
    modules = {name: mock_module(70, "district_avg") for name in STATIC_WEIGHTS}
    result = compute_regeneration_score(modules)

    for name, entry in result["breakdown"].items():
        if name == "_conflicts":
            continue
        assert "confidence_explanation" in entry, f"{name}'s breakdown entry is missing confidence_explanation"
    print("[PASS] test_confidence_breakdown_carries_per_module_explanation")


def test_dynamic_weights_wired_into_engine() -> None:
    """Rain-fed + no soil test should shift weight away from M5/M3 and toward M1/M2/M4, changing the final score."""
    raw = {name: mock_module(70) for name in STATIC_WEIGHTS}
    raw["M5_irrigation"] = mock_module(20)  # deliberately weak, so de-weighting it should raise the total

    static_result = compute_regeneration_score(raw, weights=STATIC_WEIGHTS)
    dynamic_weights = get_dynamic_weights("rainfed", has_soil_test=False)
    dynamic_result = compute_regeneration_score(raw, weights=dynamic_weights)

    assert dynamic_result["regeneration_score"] != static_result["regeneration_score"], (
        "dynamic weights should change the outcome vs static weights on the same raw data"
    )
    print(
        f"[PASS] test_dynamic_weights_wired_into_engine "
        f"(static={static_result['regeneration_score']}, dynamic/rainfed+no-soil-test={dynamic_result['regeneration_score']})"
    )


if __name__ == "__main__":
    test_all_modules_missing()
    test_one_module_missing_still_scores()
    test_extremely_high_score_tone()
    test_conflicting_modules_surfaced()
    test_weights_always_sum_to_one()
    test_improvement_tip_never_negative_for_high_raw_score()
    test_dynamic_weights_always_sum_to_one()
    test_soil_and_crop_suitability_diverge_for_same_pin()
    test_soil_resolution_skips_to_state_when_district_missing()
    test_farmer_own_value_always_wins()
    test_sparse_data_triggers_low_confidence_label()
    test_confidence_breakdown_carries_per_module_explanation()
    test_dynamic_weights_wired_into_engine()
    print("\nAll edge case tests passed.")
