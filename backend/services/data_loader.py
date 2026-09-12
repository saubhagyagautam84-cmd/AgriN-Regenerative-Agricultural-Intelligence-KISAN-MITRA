"""
STEP 2 - dataset loading.

Everything that touches disk lives here. Nothing else in the backend is
allowed to open a file, so when we swap CSV/JSON for a real database later,
this is the only module that changes.

Design notes
------------
* Bad data is expected, not exceptional. A malformed row must never take the
  API down - it gets rejected, counted and reported via `GET /api/health/data`.
* Loads are cached in-process and invalidated on file mtime, so you can edit
  the CSV/JSON while uvicorn is running and just re-submit the form.
"""

from __future__ import annotations

import difflib
import json
import re
import threading
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from models.schemas import (
    CropOption,
    CropReference,
    LocationInfo,
    SoilData,
    now_iso,
)

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SOIL_CSV = DATA_DIR / "soil_health_card.csv"
CROP_JSON = DATA_DIR / "crop_reference.json"
PINCODE_CSV = DATA_DIR / "pincode_lookup.csv"

_LOCK = threading.Lock()
_CACHE: dict[str, dict[str, Any]] = {}


# --------------------------------------------------------------------------
# Soil Health Card CSV schema
# --------------------------------------------------------------------------

# CSV column -> SoilData field. Change a column name in the CSV and you only
# have to touch this dict.
SOIL_TEXT_COLUMNS: dict[str, str] = {
    "sample_id": "sample_id",
    "state": "state",
    "district": "district",
    "block": "block",
    "village": "village",
    "pincode": "pincode",
    "soil_type": "soil_type",
    "test_date": "test_date",
}

SOIL_NUMERIC_COLUMNS: dict[str, str] = {
    "N_kg_per_ha": "n_kg_per_ha",
    "P_kg_per_ha": "p_kg_per_ha",
    "K_kg_per_ha": "k_kg_per_ha",
    "pH": "ph",
    "EC_dS_per_m": "ec_ds_per_m",
    "organic_carbon_pct": "organic_carbon_pct",
    "S_ppm": "s_ppm",
    "Zn_ppm": "zn_ppm",
    "Fe_ppm": "fe_ppm",
    "Cu_ppm": "cu_ppm",
    "Mn_ppm": "mn_ppm",
    "B_ppm": "b_ppm",
}

SOIL_REQUIRED_COLUMNS = ["state", "district", "pincode", "pH"]

# Plausibility bounds - anything outside these is treated as a data-entry
# error and dropped to None rather than poisoning the recommendations.
NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "n_kg_per_ha": (0, 2000),
    "p_kg_per_ha": (0, 500),
    "k_kg_per_ha": (0, 2000),
    "ph": (2.0, 11.0),
    "ec_ds_per_m": (0, 20),
    "organic_carbon_pct": (0, 10),
    "s_ppm": (0, 200),
    "zn_ppm": (0, 100),
    "fe_ppm": (0, 200),
    "cu_ppm": (0, 100),
    "mn_ppm": (0, 200),
    "b_ppm": (0, 50),
}


class DataLoadReport(dict):
    """Plain dict subclass so it serialises straight to JSON in /api/health/data."""


# --------------------------------------------------------------------------
# Small utilities
# --------------------------------------------------------------------------


def _norm(value: Any) -> str:
    """Lowercase, collapse whitespace/punctuation. Used for all lookups."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9ऀ-ॿ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any, field: Optional[str] = None) -> Optional[float]:
    """Coerce a cell to float, returning None for blanks, 'NA', junk or out-of-range."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    if field and field in NUMERIC_BOUNDS:
        low, high = NUMERIC_BOUNDS[field]
        if not (low <= number <= high):
            return None
    return round(number, 4)


def _cached(key: str, path: Path, builder):
    """Return a cached load, rebuilding when the file's mtime changes."""
    mtime = path.stat().st_mtime if path.exists() else None
    with _LOCK:
        entry = _CACHE.get(key)
        if entry is not None and entry["mtime"] == mtime:
            return entry["value"]
        value = builder()
        _CACHE[key] = {"mtime": mtime, "value": value}
        return value


def clear_cache() -> None:
    """Force the next load to re-read from disk. Handy in tests."""
    with _LOCK:
        _CACHE.clear()


def _count_data_lines(path: Path) -> int:
    """Non-empty lines minus the header - used to detect parser-skipped rows."""
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return max(sum(1 for line in handle if line.strip()) - 1, 0)
    except OSError:
        return 0


# --------------------------------------------------------------------------
# 2a. Soil Health Card CSV
# --------------------------------------------------------------------------


def _build_soil() -> tuple[list[SoilData], DataLoadReport]:
    report = DataLoadReport(
        file=str(SOIL_CSV),
        exists=SOIL_CSV.exists(),
        loaded_at=now_iso(),
        rows_in_file=0,
        rows_parsed=0,
        rows_valid=0,
        rows_rejected=0,
        parser_skipped_lines=0,
        rejected=[],
        missing_columns=[],
        error=None,
    )

    if not SOIL_CSV.exists():
        report["error"] = f"Soil Health Card CSV not found at {SOIL_CSV}"
        return [], report

    try:
        # dtype=str keeps full control over coercion; on_bad_lines='skip' means
        # a row with the wrong number of fields is dropped instead of raising.
        frame = pd.read_csv(
            SOIL_CSV,
            dtype=str,
            skipinitialspace=True,
            on_bad_lines="skip",
            encoding="utf-8-sig",
        )
    except Exception as exc:  # noqa: BLE001 - never let a bad file kill the API
        report["error"] = f"Could not parse CSV: {type(exc).__name__}: {exc}"
        return [], report

    report["rows_in_file"] = _count_data_lines(SOIL_CSV)
    report["rows_parsed"] = int(len(frame))
    report["parser_skipped_lines"] = max(report["rows_in_file"] - report["rows_parsed"], 0)

    missing = [c for c in SOIL_REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        report["missing_columns"] = missing
        report["error"] = f"CSV is missing required column(s): {', '.join(missing)}"
        return [], report

    records: list[SoilData] = []
    for position, (_, row) in enumerate(frame.iterrows()):
        # +2 = 1 for the header line, 1 because humans count from 1
        line_number = position + 2
        raw = {col: row.get(col) for col in frame.columns}

        fields: dict[str, Any] = {}
        for column, field in SOIL_TEXT_COLUMNS.items():
            fields[field] = _clean_text(raw.get(column))
        for column, field in SOIL_NUMERIC_COLUMNS.items():
            fields[field] = _to_float(raw.get(column), field)

        pincode = (fields.get("pincode") or "").strip()
        if pincode and not re.fullmatch(r"\d{6}", pincode):
            pincode = ""
        fields["pincode"] = pincode or None

        # A record is only useful if we can locate it...
        if not fields["pincode"] and not (fields.get("district") and fields.get("state")):
            report["rejected"].append(
                {
                    "line": line_number,
                    "sample_id": fields.get("sample_id"),
                    "reason": "no usable location (needs a 6-digit pincode, or district + state)",
                }
            )
            continue

        # ...and only meaningful if at least one measurement survived coercion.
        if all(
            fields.get(f) is None
            for f in ("n_kg_per_ha", "p_kg_per_ha", "k_kg_per_ha", "ph", "organic_carbon_pct")
        ):
            report["rejected"].append(
                {
                    "line": line_number,
                    "sample_id": fields.get("sample_id"),
                    "reason": "no valid N/P/K/pH/OC measurement in the row",
                }
            )
            continue

        try:
            records.append(SoilData(match_level="none", **fields))
        except Exception as exc:  # noqa: BLE001
            report["rejected"].append(
                {
                    "line": line_number,
                    "sample_id": fields.get("sample_id"),
                    "reason": f"schema validation failed: {exc}",
                }
            )

    report["rows_valid"] = len(records)
    report["rows_rejected"] = len(report["rejected"])
    return records, report


def load_soil_records() -> tuple[list[SoilData], DataLoadReport]:
    """Parsed Soil Health Card rows plus a report on what was thrown away."""
    return _cached("soil", SOIL_CSV, _build_soil)


def load_soil_dataframe() -> pd.DataFrame:
    """The valid soil rows as a DataFrame - convenient for notebooks/ML later."""
    records, _ = load_soil_records()
    return pd.DataFrame([r.model_dump() for r in records])


def _average_records(rows: list[SoilData], match_level: str) -> SoilData:
    """Collapse several soil samples into one representative record."""
    if len(rows) == 1:
        merged = rows[0].model_copy(update={"match_level": match_level, "records_averaged": 1})
        return merged

    averaged: dict[str, Any] = {}
    for field in SOIL_NUMERIC_COLUMNS.values():
        values = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        averaged[field] = round(sum(values) / len(values), 3) if values else None

    first = rows[0]
    return SoilData(
        sample_id=f"{len(rows)} samples averaged",
        state=first.state,
        district=first.district,
        block=first.block if match_level == "exact_pincode" else None,
        village=first.village if match_level == "exact_pincode" else None,
        pincode=first.pincode if match_level == "exact_pincode" else None,
        soil_type=first.soil_type,
        test_date=max((r.test_date or "" for r in rows), default=None) or None,
        match_level=match_level,  # type: ignore[arg-type]
        records_averaged=len(rows),
        **averaged,
    )


def find_soil_record(
    pincode: Optional[str] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
) -> Optional[SoilData]:
    """
    Best available soil record for a location, degrading gracefully:
        exact pincode -> district average -> state average -> None.

    The caller can tell which happened from `SoilData.match_level` and should
    downgrade its ModuleResponse status to "partial" for anything but an
    exact match.
    """
    records, _ = load_soil_records()
    if not records:
        return None

    if pincode:
        hits = [r for r in records if r.pincode == str(pincode).strip()]
        if hits:
            return _average_records(hits, "exact_pincode")

    if district:
        target = _norm(district)
        hits = [r for r in records if _norm(r.district) == target]
        if state:
            same_state = [r for r in hits if _norm(r.state) == _norm(state)]
            hits = same_state or hits
        if hits:
            return _average_records(hits, "district")

    if state:
        target = _norm(state)
        hits = [r for r in records if _norm(r.state) == target]
        if hits:
            return _average_records(hits, "state")

    return None


# --------------------------------------------------------------------------
# 2b. Crop reference JSON
# --------------------------------------------------------------------------


def _build_crops() -> tuple[dict[str, CropReference], list[CropReference], DataLoadReport]:
    report = DataLoadReport(
        file=str(CROP_JSON),
        exists=CROP_JSON.exists(),
        loaded_at=now_iso(),
        crops_in_file=0,
        crops_valid=0,
        crops_rejected=0,
        rejected=[],
        error=None,
    )

    if not CROP_JSON.exists():
        report["error"] = f"Crop reference JSON not found at {CROP_JSON}"
        return {}, [], report

    try:
        payload = json.loads(CROP_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report["error"] = f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        return {}, [], report
    except OSError as exc:
        report["error"] = f"Could not read file: {exc}"
        return {}, [], report

    raw_crops = payload.get("crops") if isinstance(payload, dict) else payload
    if not isinstance(raw_crops, list):
        report["error"] = "Expected a top-level 'crops' array"
        return {}, [], report

    report["crops_in_file"] = len(raw_crops)

    index: dict[str, CropReference] = {}
    ordered: list[CropReference] = []
    for position, entry in enumerate(raw_crops):
        try:
            crop = CropReference.model_validate(entry)
        except Exception as exc:  # noqa: BLE001
            name = entry.get("crop_name") if isinstance(entry, dict) else None
            report["rejected"].append(
                {
                    "index": position,
                    "crop_name": name,
                    "reason": str(exc).splitlines()[0],
                }
            )
            continue

        ordered.append(crop)
        # Index the canonical name, every alias and every local name so the
        # farmer can type "dhan", "paddy" or "धान" and still hit Rice.
        keys = [crop.crop_name, *crop.aliases, *crop.local_names.values()]
        for key in keys:
            normalised = _norm(key)
            if normalised:
                index.setdefault(normalised, crop)

    report["crops_valid"] = len(ordered)
    report["crops_rejected"] = len(report["rejected"])
    return index, ordered, report


def load_crop_reference() -> tuple[dict[str, CropReference], list[CropReference], DataLoadReport]:
    return _cached("crops", CROP_JSON, _build_crops)


def find_crop(name: str) -> Optional[CropReference]:
    """Look up a crop by name, alias, local name, or a close misspelling."""
    index, ordered, _ = load_crop_reference()
    if not index:
        return None

    key = _norm(name)
    if not key:
        return None
    if key in index:
        return index[key]

    # "wheats" / "gehun " and similar
    singular = key[:-1] if key.endswith("s") else key
    if singular in index:
        return index[singular]

    # Substring: "bt cotton hybrid" -> cotton
    for candidate_key, crop in index.items():
        if candidate_key and (candidate_key in key or key in candidate_key):
            return crop

    # Last resort: fuzzy match against every known key
    close = difflib.get_close_matches(key, list(index.keys()), n=1, cutoff=0.8)
    return index[close[0]] if close else None


def list_crops() -> list[CropOption]:
    """Feeds the crop dropdown in the farmer form (`GET /api/crops`)."""
    _, ordered, _ = load_crop_reference()
    options: list[CropOption] = []
    for crop in ordered:
        season = crop.season.value if hasattr(crop.season, "value") else str(crop.season)
        options.append(
            CropOption(
                crop_name=crop.crop_name,
                local_name=crop.local_names.get("hi"),
                season=season,
            )
        )
    return sorted(options, key=lambda option: option.crop_name)


# --------------------------------------------------------------------------
# Pincode -> administrative location
# --------------------------------------------------------------------------


def _build_pincodes() -> tuple[dict[str, dict[str, Any]], DataLoadReport]:
    report = DataLoadReport(
        file=str(PINCODE_CSV),
        exists=PINCODE_CSV.exists(),
        loaded_at=now_iso(),
        rows_valid=0,
        error=None,
    )
    if not PINCODE_CSV.exists():
        report["error"] = f"Pincode lookup CSV not found at {PINCODE_CSV}"
        return {}, report

    try:
        frame = pd.read_csv(
            PINCODE_CSV, dtype=str, on_bad_lines="skip", encoding="utf-8-sig"
        )
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"Could not parse CSV: {type(exc).__name__}: {exc}"
        return {}, report

    table: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        pincode = (_clean_text(row.get("pincode")) or "").strip()
        if not re.fullmatch(r"\d{6}", pincode):
            continue
        table[pincode] = {
            "village": _clean_text(row.get("village")),
            "block": _clean_text(row.get("block")),
            "district": _clean_text(row.get("district")),
            "state": _clean_text(row.get("state")),
            "latitude": _to_float(row.get("latitude")),
            "longitude": _to_float(row.get("longitude")),
        }

    report["rows_valid"] = len(table)
    return table, report


def load_pincode_lookup() -> tuple[dict[str, dict[str, Any]], DataLoadReport]:
    return _cached("pincodes", PINCODE_CSV, _build_pincodes)


def resolve_location(
    pincode: str,
    village: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> LocationInfo:
    """
    Turn a PIN code into state/district/block + coordinates.

    TODO(integration): this hand-built CSV covers ~15 demo PIN codes. Replace
    with the full India Post PIN directory (~155k rows) or a geocoding call;
    the returned shape does not change.
    """
    table, _ = load_pincode_lookup()
    row = table.get(str(pincode).strip())

    if row is None:
        # Unknown PIN code: fall back to whatever the farmer typed plus GPS.
        return LocationInfo(
            pincode=pincode,
            village=village,
            latitude=latitude,
            longitude=longitude,
            resolved=False,
            source="farmer-entered (PIN code not in lookup table)",
        )

    return LocationInfo(
        pincode=pincode,
        # A village the farmer typed themselves beats the table's default.
        village=village or row["village"],
        block=row["block"],
        district=row["district"],
        state=row["state"],
        latitude=latitude if latitude is not None else row["latitude"],
        longitude=longitude if longitude is not None else row["longitude"],
        resolved=True,
        source="pincode_lookup.csv",
    )


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------


def data_health() -> dict[str, Any]:
    """Everything the team needs to debug a bad dataset, in one endpoint."""
    _, soil_report = load_soil_records()
    _, _, crop_report = load_crop_reference()
    _, pin_report = load_pincode_lookup()
    return {
        "checked_at": now_iso(),
        "data_dir": str(DATA_DIR),
        "soil_health_card": soil_report,
        "crop_reference": crop_report,
        "pincode_lookup": pin_report,
    }
