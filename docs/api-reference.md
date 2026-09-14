# API reference

Hand-written endpoint map and response contracts. The source of truth for
exact validation rules is always `backend/models/schemas.py` (mirrored in
`frontend/lib/types.ts`) and the live interactive docs at
`http://127.0.0.1:8001/docs` once the backend is running - this file is the
narrative version: what each endpoint is *for*, and how the pieces fit
together, which Swagger doesn't say.

## Architecture in one paragraph

A farmer submission goes through three layers. **Part A**
(`services/modules/`) is 4 independent rule-based advisory modules reading
from one merged `AggregatedData` object. **Part B** (`services/regen/`) is a
second pipeline - a Feature Resolver that walks the Geographic Confidence
Ladder for every soil/crop-suitability field, then 5 modules with real
cross-module dependencies (M1 reads M2's severity; M2's trend projection
reads M1's and M4's picks). **Part C** (`regeneration_score/`) combines
Part B's 5 module outputs into one weighted regeneration score, a 3-tier
overall confidence label, real season-over-season history, and
district-level peer comparison. All three share one request/response
convention: POST the same `FarmInput` body, get back `ModuleResponse`
envelopes.

## Endpoint map

| Method | Path | Layer | What it does |
|---|---|---|---|
| GET | `/api/health` | - | Liveness check |
| GET | `/api/health/data` | - | Dataset load report - rows read/rejected/why, see `data_loader.py` |
| GET | `/api/crops` | - | Crop list for the form dropdown |
| POST | `/api/aggregate` | Part A | Resolves location/soil/weather/crop into one `AggregatedData` object |
| POST | `/api/soil-status` | Part A | Module 1 |
| POST | `/api/irrigation-advice` | Part A | Module 2 |
| POST | `/api/crop-recommendation` | Part A | Module 3 |
| POST | `/api/rotation-suggestion` | Part A | Module 4 |
| POST | `/api/analyze` | Part A | Aggregate + all 4 modules in one round trip |
| POST | `/api/regenerate` | Part B/C | Feature Resolver + M1-M5 + Regeneration Score Engine - the main dashboard call |
| POST | `/api/crop-health-check` | Part B | Multipart photo upload -> CNN health score (Corn/Potato/Soybean only, see `FUTURE_WORK.md`) |
| GET | `/api/soil-observations/stats` | Part B | Farmer-contributed soil data loop - counts by district, see below |
| POST | `/api/sms/regenerate` | fallback channel | SMS/IVR gateway webhook - see below |
| POST | `/api/auth/verify` | auth | Exchange a Firebase Phone Auth ID token for a session token |
| GET | `/api/auth/me` | auth | Whoami |
| POST | `/api/auth/logout` | auth | Invalidate the current session |
| GET/POST/DELETE | `/api/family-members[/{id}]` | auth | Family member CRUD, requires a session |

Every POST above (except the photo upload and the SMS webhook) takes a
`FarmInput` body and every module endpoint returns a `ModuleResponse`. That
uniformity is deliberate: a new module needs zero frontend work.

## The Geographic Confidence Ladder

Every soil-chemistry field and every crop-suitability judgment carries one
of six confidence tiers, worst to best:

```
national_avg (0.35) -> state_avg (0.50) -> zone_baseline (0.60)
   -> district_avg (0.80) -> block_avg (0.90) -> observed (1.00)
```

Soil and crop suitability resolve through **two separate chains**
(`services/regen/geo_resolvers.py`) because they degrade at different
geographic rates - soil chemistry is hyper-local (skips straight from
farmer's own value to block/district/state/national), while crop
suitability's honest default is the wider agro-climatic zone. A module's
overall confidence is the WORST tier among the specific fields it depends
on (`regeneration_score/adapters.py`'s `_worst()`), and the whole score's
`confidence` label is `"High"` / `"Estimated"` / `"Low confidence - mostly
regional averages"` depending on the lowest tier used anywhere
(`score_engine.py::_overall_confidence_level`).

## The farmer-contributed soil data loop

When a farmer submits their own soil test (`soil_test_available: true` plus
at least one N/P/K/pH/organic-carbon value), `services/farmer_soil_observations.py`
persists it (deduped by exact content, geotagged via the request's resolved
location) so it densifies the block/district/state average OTHER nearby
farmers' estimates are built from - no separate submission flow, it reuses
data the farmer already typed. `GET /api/soil-observations/stats?district=`
reports the real count, split from the official Soil Health Card count, for
transparency.

## Real history and peer comparison

`RegenerationScore.history` is real (`"source": "real"`) once a second
`/api/regenerate` call exists for the same farm_id (a deterministic hash of
pincode+crop_name - see `regeneration_score/history_tracker.py`), stored in
SQLite by `services/score_history.py`; the very first submission for a
farm_id falls back to the original simulated projection. `peer_comparison`
compares the current score against OTHER real farm_ids' latest scores in
the same district, and stays `null` below `peer_comparison.py`'s
`MIN_PEERS` threshold rather than showing a comparison built on noise.

## SMS/IVR fallback channel

`POST /api/sms/regenerate` is what a real SMS gateway's inbound webhook
would call: `{"from_phone": "...", "body": "..."}` in, `{"reply_text": "...",
"understood": bool}` out. The command format and `TELEPHONY_PROVIDER`
switch (a local console simulator by default, real Twilio once configured)
are documented in `services/telephony.py`'s module docstring. Voice IVR
(an actual phone call) is not implemented - see `FUTURE_WORK.md`.
