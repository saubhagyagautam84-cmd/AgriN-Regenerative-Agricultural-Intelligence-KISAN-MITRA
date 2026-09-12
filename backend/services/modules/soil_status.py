"""
MODULE 1/4 - Soil status.

Reads : AggregatedData.soil, AggregatedData.crop_reference
Writes: ModuleResponse(module_name="soil_status")

=========================================================================
 TODO(ML): REPLACE THE BODY OF `run()` WITH A REAL MODEL
 -----------------------------------------------------------------------
 Today this is a lookup against the Government SHC rating bands plus a
 fertiliser back-calculation. A future model could predict nutrient
 availability from soil + weather + management history and set a real
 `confidence`.

 Contract to preserve:
   * signature      run(aggregated: AggregatedData) -> ModuleResponse
   * module_name    "soil_status"
   * details keys   nutrients[], ph, ec, deficiencies[], fertiliser_plan,
                    farmer_actions[]
 The dashboard card reads those keys. Add keys freely; do not rename.
=========================================================================
"""

from __future__ import annotations

from models.schemas import AggregatedData, ModuleResponse
from services.modules.common import (
    RATING_LABELS_HI,
    SHC_RATING_BANDS,
    describe_ec,
    describe_ph,
    rate_nutrient,
)

MODULE_NAME = "soil_status"

# Dose multiplier applied to the crop's standard requirement, by soil rating.
DOSE_FACTOR: dict[str, float] = {"low": 1.25, "medium": 1.0, "high": 0.75}

# Nutrient content of the common straight/complex fertilisers, by weight.
UREA_N = 0.46
DAP_P2O5 = 0.46
DAP_N = 0.18
MOP_K2O = 0.60


def run(aggregated: AggregatedData) -> ModuleResponse:
    soil = aggregated.soil
    crop = aggregated.crop_reference

    if soil is None:
        return ModuleResponse.partial(
            MODULE_NAME,
            summary=(
                "No soil test found for your area. Get a free Soil Health Card "
                "from your nearest Krishi Vigyan Kendra."
            ),
            details={
                "nutrients": [],
                "ph": None,
                "ec": None,
                "deficiencies": [],
                "fertiliser_plan": None,
                "farmer_actions": [
                    "Ask your KVK or agriculture officer for a free soil test.",
                    "Until then, follow the standard fertiliser dose printed on your seed packet.",
                ],
                "sample": None,
            },
            confidence=None,
        )

    # --- 1. rate every measured nutrient ---------------------------------
    nutrients = []
    deficiencies: list[str] = []
    for field, ((low_max, medium_max), unit, label) in SHC_RATING_BANDS.items():
        value = getattr(soil, field, None)
        if value is None:
            continue
        rating = rate_nutrient(field, value)
        nutrients.append(
            {
                "key": field,
                "label": label,
                "value": value,
                "unit": unit,
                "rating": rating,
                "rating_hi": RATING_LABELS_HI.get(rating or "", None),
                "low_below": low_max,
                "high_above": medium_max,
            }
        )
        if rating == "low":
            deficiencies.append(label)

    ph_code, ph_text = describe_ph(soil.ph)
    ec_code, ec_text = describe_ec(soil.ec_ds_per_m)

    ph_fits_crop = None
    if crop is not None and soil.ph is not None:
        ph_fits_crop = crop.ideal_soil_ph.min <= soil.ph <= crop.ideal_soil_ph.max

    # --- 2. back-calculate a fertiliser plan ------------------------------
    # TODO(ML): a soil-test-crop-response (STCR) model would replace this
    # with target-yield-based doses instead of flat +/-25% adjustments.
    fertiliser_plan = None
    if crop is not None:
        n_factor = DOSE_FACTOR.get(rate_nutrient("n_kg_per_ha", soil.n_kg_per_ha) or "medium", 1.0)
        p_factor = DOSE_FACTOR.get(rate_nutrient("p_kg_per_ha", soil.p_kg_per_ha) or "medium", 1.0)
        k_factor = DOSE_FACTOR.get(rate_nutrient("k_kg_per_ha", soil.k_kg_per_ha) or "medium", 1.0)

        n_dose = crop.n_requirement_kg_per_ha * n_factor
        p_dose = crop.p_requirement_kg_per_ha * p_factor
        k_dose = crop.k_requirement_kg_per_ha * k_factor

        area = aggregated.land_size_hectare
        dap_kg = p_dose / DAP_P2O5
        urea_kg = max(0.0, (n_dose - dap_kg * DAP_N)) / UREA_N  # DAP already supplies some N
        mop_kg = k_dose / MOP_K2O

        fertiliser_plan = {
            "basis": "ICAR standard dose adjusted for your soil test rating",
            "per_hectare": {
                "N_kg": round(n_dose, 1),
                "P2O5_kg": round(p_dose, 1),
                "K2O_kg": round(k_dose, 1),
            },
            "for_your_field": {
                "area_hectare": area,
                "urea_kg": round(urea_kg * area, 1),
                "dap_kg": round(dap_kg * area, 1),
                "mop_kg": round(mop_kg * area, 1),
                "urea_bags_45kg": round(urea_kg * area / 45, 1),
                "dap_bags_50kg": round(dap_kg * area / 50, 1),
                "mop_bags_50kg": round(mop_kg * area / 50, 1),
            },
            "note": "Split nitrogen: half at sowing, rest at first and second irrigation.",
        }

    # --- 3. farmer-readable actions ---------------------------------------
    actions: list[str] = []
    if deficiencies:
        actions.append(f"Your soil is low in {', '.join(deficiencies)}. Correct this before sowing.")
    if ph_code in ("strongly_acidic", "slightly_acidic"):
        actions.append("Apply lime as advised by your KVK to bring pH up.")
    if ph_code in ("alkaline", "strongly_alkaline"):
        actions.append("Apply gypsum and add farmyard manure to bring pH down slowly.")
    if soil.organic_carbon_pct is not None and soil.organic_carbon_pct < 0.5:
        actions.append("Add 5 tonnes/acre of farmyard manure or compost - your soil is low on organic matter.")
    if ec_code != "normal" and ec_code != "unknown":
        actions.append("Improve field drainage; salt is building up in your soil.")
    if ph_fits_crop is False and crop is not None:
        actions.append(
            f"Your soil pH ({soil.ph}) is outside the ideal range for "
            f"{crop.crop_name} ({crop.ideal_soil_ph.min}-{crop.ideal_soil_ph.max})."
        )
    if not actions:
        actions.append("Your soil is in good shape. Follow the standard fertiliser dose.")

    # --- 4. summary + status ---------------------------------------------
    if deficiencies:
        shortlist = ", ".join(deficiencies[:2])
        summary = f"Soil is low in {shortlist}. {ph_text}."
    else:
        summary = f"Soil nutrients look adequate. {ph_text}."

    # An exact PIN-code match is "ok"; a district/state average is "partial".
    status_is_exact = soil.match_level == "exact_pincode"
    details = {
        "sample": {
            "sample_id": soil.sample_id,
            "match_level": soil.match_level,
            "records_averaged": soil.records_averaged,
            "village": soil.village,
            "block": soil.block,
            "district": soil.district,
            "state": soil.state,
            "soil_type": soil.soil_type,
            "test_date": soil.test_date,
            "source": soil.source,
        },
        "nutrients": nutrients,
        "ph": {"value": soil.ph, "code": ph_code, "text": ph_text, "fits_crop": ph_fits_crop},
        "ec": {"value": soil.ec_ds_per_m, "code": ec_code, "text": ec_text},
        "deficiencies": deficiencies,
        "fertiliser_plan": fertiliser_plan,
        "farmer_actions": actions,
        "is_dummy_data": True,  # TODO(ML): flip to False when a real model lands
    }

    if status_is_exact:
        return ModuleResponse.ok(MODULE_NAME, summary, details, confidence=None)
    return ModuleResponse.partial(
        MODULE_NAME,
        summary=f"{summary} (Based on a {soil.match_level.replace('_', ' ')} average, not your own field.)",
        details=details,
        confidence=None,
    )
