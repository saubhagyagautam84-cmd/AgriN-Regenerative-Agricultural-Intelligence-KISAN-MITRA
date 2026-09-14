"""
The farmer-contributed soil data loop.

Every time a farmer fills in their own soil test values (the existing
`soil_test_available=True` + `soil_test_n_kg_per_ha`/etc. fields on
FarmInput - see models/schemas.py), that IS a real, geotagged soil
observation. Until now it was used once, for that one farmer's own
"observed" tier in the Geographic Confidence Ladder (services/regen/
geo_resolvers.py), then thrown away. This module persists it (same SQLite
file/pattern as services/auth.py and services/score_history.py) so it can
also densify the block/district/state averages OTHER nearby farmers'
estimates are built from - closing the loop without asking for a single new
form field.

Two honesty guards, both deliberate:

1. Deduplication by content hash (pincode + all five values). A farmer
   resubmitting the exact same reading - most commonly an automated test
   or a farmer just re-checking their report - is not new information and
   must not inflate the sample count. A genuinely different reading (a new
   test, a different field) always gets its own row.

2. geo_resolvers.py (not this module) is responsible for disclosing the
   official/farmer-submitted split in its `detail` trace string whenever it
   blends these in - a crowdsourced reading is never silently presented as
   equivalent to a certified Soil Health Card row.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.sqlite3"


_schema_ready = False


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Lazily self-initializing (not just via main.py's startup lifespan)
        # so regeneration_score/test_edge_cases.py and other standalone
        # scripts that import geo_resolvers.py directly - without ever
        # running the FastAPI app - still work. init_db() below stays as
        # the explicit, idempotent call main.py's lifespan makes.
        global _schema_ready
        if not _schema_ready:
            init_db(conn)
            _schema_ready = True
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(_conn: Optional[sqlite3.Connection] = None) -> None:
    ddl = """
        CREATE TABLE IF NOT EXISTS farmer_soil_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT UNIQUE NOT NULL,
            pincode TEXT,
            block TEXT,
            district TEXT,
            state TEXT,
            n_kg_per_ha REAL,
            p_kg_per_ha REAL,
            k_kg_per_ha REAL,
            ph REAL,
            organic_carbon_pct REAL,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_farmer_soil_district
            ON farmer_soil_observations(district, state);
        """
    global _schema_ready
    if _conn is not None:
        _conn.executescript(ddl)
        _schema_ready = True
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(ddl)
        conn.commit()
    finally:
        conn.close()
    _schema_ready = True


def _content_hash(pincode: Optional[str], n: Optional[float], p: Optional[float], k: Optional[float], ph: Optional[float], oc: Optional[float]) -> str:
    key = f"{pincode}|{n}|{p}|{k}|{ph}|{oc}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def record_observation(
    pincode: Optional[str],
    block: Optional[str],
    district: Optional[str],
    state: Optional[str],
    n_kg_per_ha: Optional[float],
    p_kg_per_ha: Optional[float],
    k_kg_per_ha: Optional[float],
    ph: Optional[float],
    organic_carbon_pct: Optional[float],
) -> bool:
    """Returns True if a new row was actually inserted (False = exact duplicate, ignored)."""
    if all(v is None for v in (n_kg_per_ha, p_kg_per_ha, k_kg_per_ha, ph, organic_carbon_pct)):
        return False
    content_hash = _content_hash(pincode, n_kg_per_ha, p_kg_per_ha, k_kg_per_ha, ph, organic_carbon_pct)
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO farmer_soil_observations
                (content_hash, pincode, block, district, state,
                 n_kg_per_ha, p_kg_per_ha, k_kg_per_ha, ph, organic_carbon_pct, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (content_hash, pincode, block, district, state, n_kg_per_ha, p_kg_per_ha, k_kg_per_ha, ph, organic_carbon_pct, int(time.time())),
        )
        return cursor.rowcount > 0


@dataclass
class FarmerObservation:
    """Attribute names deliberately mirror models.schemas.SoilData's numeric fields, so
    services/regen/geo_resolvers.py's _average() (which just does getattr(record, field_name))
    works unchanged against a mixed list of SoilData + FarmerObservation records."""

    district: Optional[str]
    state: Optional[str]
    block: Optional[str]
    n_kg_per_ha: Optional[float]
    p_kg_per_ha: Optional[float]
    k_kg_per_ha: Optional[float]
    ph: Optional[float]
    organic_carbon_pct: Optional[float]


def list_observations(district: Optional[str] = None, state: Optional[str] = None) -> list[FarmerObservation]:
    """All farmer-submitted observations, optionally filtered - used by geo_resolvers.py to blend in, and by /api/soil-observations/stats for transparency."""
    query = "SELECT district, state, block, n_kg_per_ha, p_kg_per_ha, k_kg_per_ha, ph, organic_carbon_pct FROM farmer_soil_observations"
    clauses, params = [], []
    if district:
        clauses.append("district = ?")
        params.append(district)
    if state:
        clauses.append("state = ?")
        params.append(state)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [FarmerObservation(**dict(row)) for row in rows]


def count_observations(district: Optional[str] = None, state: Optional[str] = None) -> int:
    return len(list_observations(district=district, state=state))
