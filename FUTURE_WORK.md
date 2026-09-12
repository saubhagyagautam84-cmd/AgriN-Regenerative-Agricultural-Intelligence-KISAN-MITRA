# Future work

Tracked gaps that are genuine scope limitations, not bugs - each one needs a
deliberate decision (new data, new infrastructure, or a product call) before
it can be closed, so it's recorded here rather than left as an undocumented
silent limitation.

---

## Expand the crop-health CNN beyond Corn, Potato, Soybean

**Current state**: `backend/services/regen/cnn_health.py`'s trained model
only recognises 3 of Kisan Sathi's 18 crops, because PlantVillage (the
dataset it was trained on) only covers 14 crop species total, and only
those 3 overlap with this project's crop list. Every other crop's photo
gets an honest `label: "unsupported_crop"` placeholder rather than a
guessed classification - see `is_supported_crop()` in that file.

**Why it's not fixed here**: no labelled disease-image dataset covering
Wheat, Rice, Cotton, Sugarcane, Mustard, Chickpea, Groundnut, Pearl Millet,
Lentil, Pigeon Pea, Green Gram, Black Gram, Sorghum, Barley or Sunflower
was available in this environment.

**Recommended next step**: [PlantDoc](https://github.com/pratikkayal/PlantDoc-Dataset)
covers a wider crop set with real field-condition photos (vs.
PlantVillage's lab-controlled backgrounds, which don't generalise well to
farmer-taken photos anyway). Combine both datasets, retrain following the
same pattern as `backend/cnn_training/train_lowmem.py`, and update
`SUPPORTED_CROP_KEYWORDS` in `cnn_health.py` once validated - everything
downstream (the subprocess bridge, M1/M3's consumption of `crop_health_score`,
the frontend copy) already expects exactly this shape and needs no changes.

---

## `npk_stage_split.json` is category-level, not per-crop

**Current state**: `backend/data/npk_stage_split.json` groups the 18 crops
into 4 categories (cereal, legume, long-duration cash crop, oilseed/root)
with one split pattern per category, rather than a bespoke split for each
individual crop.

**Why it's not fixed here**: per-crop stage-split field trial data wasn't
available to compile honestly; the category patterns are standard taught
ICAR practice, not fabricated numbers, but they're a real simplification.

**Recommended next step**: source per-crop fertiliser scheduling from each
crop's specific ICAR institute handbook (already cited per-crop in
`crop_reference.json`'s `source` field) and replace the category lookup in
`m3_fertilizer.py`'s `_stage_split_pct()` with a per-crop one.

---

## ~~Weather is still a synthetic stub~~ - RESOLVED

`backend/services/weather.py` now calls Open-Meteo live (real ET0/rainfall/
forecast, no API key). Kept here struck through rather than deleted so the
resolution is traceable in this file's history.

---

## Soil Health Card data is a hand-compiled placeholder, not real data.gov.in data

**Current state**: `backend/data/soil_health_card.csv` (20 rows, 5 states)
is manually authored, not sourced from data.gov.in.

**Why it's not fixed here**: data.gov.in's district-wise Soil Health Card
datasets aren't published as a single clean, consistently-formatted,
queryable dataset/API across states - coverage and column format vary by
state release. Attempting to wire this in reliably was judged higher
effort/lower certainty than the payoff for this stage; accepted as a
documented limitation instead of a fragile scrape.

**Recommended next step**: identify 2-3 states with a clean CSV export on
data.gov.in's Soil Health Card portal, hand-verify the column mapping
against `services/data_loader.py`'s `SOIL_TEXT_COLUMNS`/`SOIL_NUMERIC_COLUMNS`,
and replace the placeholder rows for just those states first rather than
attempting full national coverage in one pass.
