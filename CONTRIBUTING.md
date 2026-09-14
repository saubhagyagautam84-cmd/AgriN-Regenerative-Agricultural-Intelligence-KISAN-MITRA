# Contributing to Kisan Mitra

Thanks for looking at this project. It's a farmer-facing advisory tool
(soil, irrigation, crop rotation, fertiliser, a regeneration score), built
in three layers - this doc is a map of those layers, the conventions that
hold them together, and what a PR is expected to do before it's ready.

## Project shape

```
backend/
  main.py                     FastAPI app - every route is registered here
  models/schemas.py           THE shared contract (Pydantic) - mirrored by hand in frontend/lib/types.ts
  services/
    data_loader.py            all disk I/O (CSV/JSON) lives here, nowhere else
    modules/                  Part A - 4 rule-based advisory modules (soil/irrigation/crop-rec/rotation)
    regen/                    Part B - Feature Resolver, geo resolution, M1-M5, the CNN bridge
    auth.py, score_history.py,
    farmer_soil_observations.py,
    telephony.py               SQLite-backed services (single file, see auth.py's own docstring on why)
  regeneration_score/         Part C - the Regeneration Score Engine (weights, confidence, history, peer comparison)
  smoke_test.py                end-to-end check - see "Testing" below

frontend/
  app/page.tsx                the one dashboard page, drives Part A + Part B calls
  components/                 one component per card/modal; RegenScoreCard.tsx is the Part C dashboard
  lib/api.ts                  the ONLY file that calls fetch() - swap transport here, nowhere else
  lib/types.ts                hand-mirrors backend/models/schemas.py - keep both in sync in the same commit
  lib/i18n/translations/      9 languages (en, hi, pa, mr, gu, bn, ta, te, kn) - every UI-facing key must exist in all 9

docs/field-spec.md            generated from FarmInput - do not hand-edit, re-run scripts/generate_field_spec.py
docs/api-reference.md         hand-written endpoint map + response contracts (this file's companion)
FUTURE_WORK.md                genuine scope gaps, each with why it's not fixed and what closing it needs
```

## Conventions this codebase already enforces - follow them, don't fight them

1. **Never fabricate data.** If a real dataset/API/account isn't available,
   say so honestly (an explicit `null`, a clear message, a `FUTURE_WORK.md`
   entry) rather than inventing a plausible-looking number, phone number, or
   contact detail. See `ContactModal.tsx`'s pending-note and
   `services/auth.py`'s 503-until-configured pattern for the house style.
2. **One shared response envelope.** Every Part A module returns exactly
   `ModuleResponse` (`models/schemas.py`); the frontend renders any of them
   with one `ModuleCard` component. A new module needs zero frontend
   changes if it keeps this shape.
3. **Confidence is geographic, not binary.** `regeneration_score/confidence.py`'s
   6-level ladder (national_avg → state_avg → zone_baseline → district_avg →
   block_avg → observed) is deliberately two SEPARATE resolution chains
   (`services/regen/geo_resolvers.py`) - soil chemistry and crop suitability
   degrade at different geographic rates. Don't merge them back into one
   function; don't add a new data source without deciding which chain (or
   neither) it belongs to.
4. **Bad input data degrades, it doesn't crash.** `data_loader.py` rejects
   and counts malformed rows (`GET /api/health/data`) instead of raising;
   `services/regen/pipeline.py`'s `_safe()` wrapper means one broken module
   never takes down the other four.
5. **Dynamic backend-generated prose stays English.** Per-module
   `confidence_explanation`, peer-comparison `summary` text, etc. are
   generated server-side and intentionally not translated (see
   `score_engine.py`'s inline comment) - only static UI labels go through
   `lib/i18n`. Don't "fix" this by adding i18n calls around generated text.
6. **`types.ts` and `schemas.py` change together.** Nothing enforces this
   automatically yet (see the `TODO(tooling)` at the top of `types.ts`) - if
   you change a Pydantic model's shape, update the TypeScript interface in
   the same commit.

## Adding things

- **A new Part A/B module**: read from `AggregatedData` (or the enriched
  feature vector for Part B), return a `ModuleResponse`. Wire it into
  `services/modules/__init__.py` (Part A) or `services/regen/pipeline.py`
  (Part B). Add its route in `main.py`, a smoke-test assertion, and a
  frontend `ModuleCard` title/translation.
- **A new language**: copy `lib/i18n/translations/en.ts`'s key structure
  into a new file, add it to `lib/i18n/translations/index.ts` and
  `lib/languages.ts`. TypeScript will refuse to compile if a key is
  missing (`TranslationShape = typeof en`) - that's the safety net, don't
  work around it with `as any`.
- **A new geographic data source** (another soil/crop dataset, another
  admin level): decide first whether it's a soil-chemistry signal or a
  crop-suitability signal (see point 3 above), then extend the matching
  resolver in `geo_resolvers.py`, not a new parallel system.
- **A telephony provider** (real SMS/IVR): `services/telephony.py`'s
  `send_sms()` already branches on `TELEPHONY_PROVIDER` - add one more
  branch there. Don't add a new call site elsewhere.

## Testing

Three layers, one command:

```bash
./verify.sh   # from the repo root, Git Bash - needs backend on :8001 and frontend on :3000 already running
```

1. `regeneration_score/test_edge_cases.py` - Part C unit tests, no server needed.
2. `backend/smoke_test.py` - real HTTP requests against every route (Part A + B), including the confidence ladder, the farmer-contributed soil loop, real vs. simulated history, peer comparison, and the SMS fallback channel.
3. Playwright (`frontend/tests/*.spec.ts`) - the dashboard in a real browser, across languages and themes.

**A pre-commit hook checks that every FastAPI route in `main.py` is
referenced somewhere in `smoke_test.py`.** A new endpoint with no smoke-test
coverage will fail the commit, not silently ship untested.

## Before opening a PR

- [ ] `verify.sh` passes end to end
- [ ] `npx tsc --noEmit` in `frontend/` is clean
- [ ] Any new UI-facing string exists in all 9 `lib/i18n/translations/*.ts` files
- [ ] Any new Pydantic field in `models/schemas.py` has a matching field in `lib/types.ts`
- [ ] A genuine scope limitation (no real dataset/account/API for something) is documented in `FUTURE_WORK.md`, not silently shipped as if complete
- [ ] `python scripts/generate_readme.py` and `python scripts/generate_field_spec.py` are re-run if the file tree or `FarmInput` changed
