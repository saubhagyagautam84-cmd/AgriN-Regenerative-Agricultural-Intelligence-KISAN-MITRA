"""
Regenerates docs/field-spec.md entirely from backend/models/schemas.py.

`FarmInput` (a Pydantic model) is already the single source of truth for
both runtime validation (FastAPI enforces it on every request) and this
documentation - introspecting `FarmInput.model_fields` means a new field, a
changed constraint, or an updated description can never silently drift out
of the docs again. Nobody should hand-edit docs/field-spec.md directly;
change schemas.py and re-run this script.

Sections 2-4 (auto-fetched fields, validation pairing, deferred fields)
describe things that live outside a single Pydantic model (other schemas,
paired client/server files, future-work notes) and are written once here as
templates rather than introspected - still generated output, just not
schema-derived for those specific sections.

Usage:
    backend/.venv/Scripts/python.exe scripts/generate_field_spec.py          # write
    backend/.venv/Scripts/python.exe scripts/generate_field_spec.py --check  # CI/pre-commit
"""

from __future__ import annotations

import enum
import sys
from pathlib import Path
from typing import get_args, get_origin

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FIELD_SPEC_PATH = REPO_ROOT / "docs" / "field-spec.md"

sys.path.insert(0, str(BACKEND_DIR))


def _render_type(annotation) -> str:
    origin = get_origin(annotation)
    if origin is not None:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _render_type(args[0]) + " (optional)"
        return " | ".join(_render_type(a) for a in args)
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        values = " \\| ".join(f"`{member.value}`" for member in annotation)
        return f"enum: {values}"
    return getattr(annotation, "__name__", str(annotation))


def _render_constraints(field_info) -> str:
    parts = []
    for meta in getattr(field_info, "metadata", []):
        cls_name = type(meta).__name__
        if cls_name == "Ge":
            parts.append(f">= {meta.ge}")
        elif cls_name == "Le":
            parts.append(f"<= {meta.le}")
        elif cls_name == "Gt":
            parts.append(f"> {meta.gt}")
        elif cls_name == "Lt":
            parts.append(f"< {meta.lt}")
        elif cls_name == "MinLen":
            parts.append(f"min length {meta.min_length}")
        elif cls_name == "MaxLen":
            parts.append(f"max length {meta.max_length}")
    return ", ".join(parts)


def generate_manual_inputs_table() -> str:
    from models.schemas import FarmInput

    lines = ["| field_name | type | required | validation_rule | description |", "|---|---|---|---|---|"]
    for name, field_info in FarmInput.model_fields.items():
        type_str = _render_type(field_info.annotation)
        required = "**yes**" if field_info.is_required() else "no"
        constraints = _render_constraints(field_info)
        description = (field_info.description or "").replace("\n", " ")
        lines.append(f"| `{name}` | {type_str} | {required} | {constraints or '—'} | {description or '—'} |")
    return "\n".join(lines)


DOCUMENT_TEMPLATE = """# Field specification

**Generated from `backend/models/schemas.py`'s `FarmInput` model by
`scripts/generate_field_spec.py` - do not hand-edit this file.** Change the
Pydantic model (the same one FastAPI validates every request against) and
re-run the script; nothing here can drift out of sync with actual validation
behaviour because there's only one definition.

The design rule: **the farmer types the minimum, the system derives the
rest.** Anything that can be looked up from a PIN code or a crop name is
looked up, never asked. Part B added the optional soil-test values and the
crop photo health check on top of Part A's original fields.

---

## 1. Manual inputs (the farmer enters these)

{manual_inputs_table}

**Why these and not more.** Target users may have low digital literacy, so
every extra field is a drop-off. Soil pH, NPK, rainfall, crop water needs and
rotation rules are all derivable — asking for them would be both harder for the
farmer and less accurate than a lookup. Part B's soil-test fields are the one
exception: if the farmer already has the numbers, using them beats a district
average, so they're offered as optional overrides, never required.

**Why `sowing_date` and `irrigation_source` have no "missing" fallback.**
The original Feature Resolver design called for a fallback on every
auto-derivable field, including estimating a missing sowing date from the
crop's typical sowing window and defaulting a missing water source to a
regional rainfall assumption. Neither branch exists in the code, and that's
deliberate, not an oversight: both fields are **required** (sowing_date) or
**default-valued** (irrigation_source defaults to `rainfed`) in the form
contract itself, per Part A's "ask the minimum, four things" design - so
there is never a "missing" case for the Feature Resolver to catch. Building
dead fallback code that can structurally never execute would be worse than
not building it. If a genuinely optional entry mode is ever added for
either field, the fallback logic described in the original spec is exactly
what should be built then.

---

## 2. Auto-fetched (the system derives these)

| field_name | type | source | looked up by | fallback when missing |
|---|---|---|---|---|
| `location.state` / `.district` / `.block` / `.village` | string | `data/pincode_lookup.csv` | `pincode` | `resolved: false`, farmer-entered village kept, warning attached |
| `location.latitude` / `.longitude` | number | `data/pincode_lookup.csv` | `pincode` | GPS value if the farmer shared it, else `null` |
| `soil.*` (N, P, K, pH, EC, OC, S, Zn, Fe, Cu, Mn, B) | number | `data/soil_health_card.csv` | `pincode` → district → state | Degrades exact → district avg → state avg → `null`; `match_level` records which, and modules downgrade to `status: "partial"` |
| `soil.soil_type`, `.test_date`, `.sample_id` | string | `data/soil_health_card.csv` | same | `null` |
| `weather.*` (temp, humidity, rainfall 7d/30d, forecast, ET0) | number | `services/weather.py` **(live - Open-Meteo)** | `location` lat/lon (PIN lookup or GPS) | No coordinates, or the API call fails/times out -> module returns `status: "error"`; the rest of the dashboard still renders |
| `crop_reference.*` (NPK requirement, water mm, ideal pH, rotation + cover-crop lists, duration, critical stages) | mixed | `data/crop_reference.json` | `crop_name` + aliases + Hindi names + fuzzy | `null`; advice becomes generic and `status: "partial"` |
| `land_size_hectare` | number | computed | `land_size` × `land_unit` | — |
| `days_since_sowing` | int | computed | `today − sowing_date` (negative if not yet sown) | — |
| `crop_stage_hint` | string | computed | `days_since_sowing / growth_duration_days` | `unknown` |
| `completeness` | float | computed | fraction of the 4 sources resolved | — |
| **Part B** `resolved soil (N/P/K/pH/OC)` | number + confidence | `services/regen/feature_resolver.py` | farmer-entered → SHC exact → SHC district/state → crop-standard default | Each field tagged `observed` or `estimated`; feeds the Regeneration Score's confidence breakdown |
| **Part B** `crop_health_score` | float 0-1 | `services/regen/cnn_health.py` (subprocess to the trained CNN) | uploaded photo, only for Corn/Potato/Soybean | `1.0` baseline assumed, tagged `estimated`, if no photo, unsupported crop, or the model isn't available |

---

## 3. Validation: client and server

Both sides enforce the same rules. The client copy exists only to save the
farmer a round trip — **the server never trusts it.**

| rule | client | server |
|---|---|---|
| PIN code shape | `components/FarmInputForm.tsx` → `validate()` | `models/schemas.py` → `_validate_pincode` |
| Land size range | `validate()` | `Field(gt=0, le=10_000)` |
| Crop name present | `validate()` | `Field(min_length=2)` + `_clean_crop_name` |
| Sowing date ±1 year | `validate()` | `_sane_sowing_date` |
| Enum membership | tap targets only offer valid values | Pydantic enums |
| Soil test N/P/K/pH/organic carbon ranges (Part B) | `NumberField` inputs, numeric-only | `Field(ge=..., le=...)` on each `soil_test_*` field |
| Crop health score range (Part B) | n/a - set from `/api/crop-health-check`'s response, never typed by hand | `Field(ge=0.0, le=1.0)` |

A server-side failure returns HTTP 422 in this shape, which the form renders
under the offending field:

```json
{{
  "status": "error",
  "message": "Some details need fixing before we can continue.",
  "errors": [{{ "field": "pincode", "message": "PIN code must be exactly 6 digits..." }}],
  "timestamp": "2026-09-10T17:01:59Z"
}}
```

---

## 4. Deliberately deferred

Not asked for now, but the shape leaves room:

- **Previous season's crop** — would sharpen rotation advice a lot. Currently
  inferred as "the crop you entered". Add as an optional field when we test
  with real farmers.
- **Target yield** — needed for proper STCR fertiliser maths.
- **Sowing method / variety** — affects duration and water need.
- **Phone number** — needed only when SMS/IVR advisory is added.
- **Video upload** — the crop-health CNN only ever takes a single frame, so
  photo upload is deliberately the only supported input; video was dropped
  from scope rather than deferred as "not yet built".
"""


def main() -> int:
    check_only = "--check" in sys.argv

    generated = DOCUMENT_TEMPLATE.format(manual_inputs_table=generate_manual_inputs_table())

    if FIELD_SPEC_PATH.exists():
        original = FIELD_SPEC_PATH.read_text(encoding="utf-8")
    else:
        original = None

    if generated == original:
        print("docs/field-spec.md is up to date.")
        return 0

    if check_only:
        print("docs/field-spec.md is STALE - run scripts/generate_field_spec.py to regenerate.")
        return 1

    FIELD_SPEC_PATH.write_text(generated, encoding="utf-8")
    print("docs/field-spec.md regenerated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
