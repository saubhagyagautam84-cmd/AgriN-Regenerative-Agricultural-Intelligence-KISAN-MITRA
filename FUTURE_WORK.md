# Future work

Tracked gaps that are genuine scope limitations, not bugs - each one needs a
deliberate decision (new data, new infrastructure, or a product call) before
it can be closed, so it's recorded here rather than left as an undocumented
silent limitation.

---

## Expand the crop-health CNN beyond Corn, Potato, Soybean

**Current state**: `backend/services/regen/cnn_health.py`'s trained model
only recognises 3 of Kisan Mitra's 18 crops, because PlantVillage (the
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

---

## Login (phone OTP) needs a real Firebase project to actually send SMS

**Current state**: the 3-dot menu's Login modal, `lib/auth/AuthContext.tsx`
(Firebase Phone Auth client flow), and the backend's `/api/auth/verify` +
`/api/auth/me` + SQLite session/user tables (`backend/services/auth.py`) are
all fully built and tested (see `tests/wizard_check.spec.ts`). What's
missing is a live Firebase project: without `NEXT_PUBLIC_FIREBASE_*` (frontend)
and `FIREBASE_PROJECT_ID` (backend) set, the modal says so plainly and
`/api/auth/verify` returns 503 - neither pretends to log someone in.

**Why it's not fixed here**: creating a Firebase project and enabling Phone
Auth is an account-level action only the project owner can do.

**Recommended next step**: console.firebase.google.com -> new project ->
Build -> Authentication -> Sign-in method -> enable Phone -> Project settings
-> General -> add a Web app -> copy its config into
`frontend/.env.local` (see `.env.local.example`) and the same project ID into
`backend/.env` (see `backend/.env.example`). No code changes needed.

---

## Contact-us details are a placeholder, not real support info

**Current state**: `components/ContactModal.tsx` shows an honest "not set up
yet" note rather than the fabricated helpline/email
`kisan-sathi-frontend.html`'s prototype ships (`1800-XXX-XXXX`,
`help@kisansathi.example`) - those looked real enough to be mistaken for
genuine contact details, which is worse than admitting the gap.

**Recommended next step**: once real support contact details exist, put them
in `contactModal.pendingNote`'s place across all 9
`frontend/lib/i18n/translations/*.ts` files, replacing the pending-note copy
with the actual phone/email.

---

## Family members and Login are single-farm, not multi-farm-per-account

**Current state**: `backend/services/auth.py`'s schema is user -> family
members, flat - a logged-in phone number has one shared family-member list,
not a list of farms each with its own members.

**Why it's not fixed here**: the master prompt's brief didn't specify a
multi-farm data model, and Part A/B/C's `FarmInput` itself has no persistent
"farm" entity yet (every analysis is stateless, keyed only by the request) -
inventing a farm/ownership model wasn't asked for and would be a real
product decision, not an integration detail.

**Recommended next step**: if farms need to become persistent, first-class
entities (so "family member" means "someone attached to farm X"), design
that schema change together with whoever owns the product decision, rather
than retrofitting it under the family-members feature alone.
