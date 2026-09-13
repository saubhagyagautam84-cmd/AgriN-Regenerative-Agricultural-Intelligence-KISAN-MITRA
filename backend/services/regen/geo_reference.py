"""
Geographic reference table - PIN code -> district/state/agro-climatic zone.

Backs the Geographic Confidence Ladder (see geo_resolvers.py): soil data and
crop-suitability data degrade at different geographic rates for real
agronomic reasons (soil chemistry is hyper-local; crop suitability tracks
climate, which is stable across a whole agro-climatic zone). Both resolver
chains read location context from here.

Deliberately covers only the PIN codes this project's demo dataset already
supports (see backend/data/pincode_lookup.csv) - not a national PIN
directory. Zone assignments are the Planning Commission of India's standard
15 ICAR agro-climatic zones, a real public classification, at district
granularity.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

GEO_REFERENCE_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "geo_reference.json"

_LOCK = threading.Lock()
_CACHE: dict[str, object] = {}


@dataclass
class GeoInfo:
    pin_code: str
    village_or_block: Optional[str]
    district: Optional[str]
    state: Optional[str]
    agro_climatic_zone: Optional[str]
    agro_climatic_zone_id: Optional[str]


def _load() -> dict[str, GeoInfo]:
    if not GEO_REFERENCE_JSON.exists():
        return {}
    try:
        payload = json.loads(GEO_REFERENCE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    table: dict[str, GeoInfo] = {}
    for entry in payload.get("locations", []):
        pin = str(entry.get("pin_code") or "").strip()
        if not pin:
            continue
        table[pin] = GeoInfo(
            pin_code=pin,
            village_or_block=entry.get("village_or_block"),
            district=entry.get("district"),
            state=entry.get("state"),
            agro_climatic_zone=entry.get("agro_climatic_zone"),
            agro_climatic_zone_id=entry.get("agro_climatic_zone_id"),
        )
    return table


def load_geo_reference() -> dict[str, GeoInfo]:
    """Cached in-process, invalidated on file mtime - same pattern as services/data_loader.py."""
    mtime = GEO_REFERENCE_JSON.stat().st_mtime if GEO_REFERENCE_JSON.exists() else None
    with _LOCK:
        entry = _CACHE.get("table")
        if entry is not None and _CACHE.get("mtime") == mtime:
            return entry  # type: ignore[return-value]
        table = _load()
        _CACHE["table"] = table
        _CACHE["mtime"] = mtime
        return table


def get_geo_info(pin_code: Optional[str]) -> Optional[GeoInfo]:
    """The zone/district/state for a PIN code, or None if it's outside this demo's coverage."""
    if not pin_code:
        return None
    return load_geo_reference().get(str(pin_code).strip())


def clear_cache() -> None:
    """Force the next load to re-read from disk. Handy in tests."""
    with _LOCK:
        _CACHE.clear()
