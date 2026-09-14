"""
Real season-over-season score history - upgrades regeneration_score's
simulated "last season" trend (history_tracker.py) to actual stored
snapshots once at least one real prior submission exists for this farm_id.

Uses the same SQLite file and connection pattern as services/auth.py
(single-file, zero external services - see that module's own docstring for
why). Deliberately keyed by farm_id (a deterministic hash of
pincode+crop_name, from regeneration_score/history_tracker.py), NOT by
logged-in user: a farmer's login status shouldn't gate whether their own
repeated visits to the same field+crop combination start building real
history - this mirrors exactly what the pre-existing simulated fallback
already assumed "the same farm" meant, just backed by a real table instead
of a formula. history_tracker.py's simulation stays in place as the
fallback for the very first submission, when no real prior point exists yet.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.sqlite3"

DEFAULT_HISTORY_LIMIT = 8


_schema_ready = False


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Lazily self-initializing so standalone scripts (e.g.
        # regeneration_score/test_edge_cases.py) that never go through
        # main.py's startup lifespan still work - see
        # services/farmer_soil_observations.py's identical pattern.
        global _schema_ready
        if not _schema_ready:
            _init_schema(conn)
            _schema_ready = True
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS score_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farm_id TEXT NOT NULL,
            pincode TEXT NOT NULL,
            crop_name TEXT NOT NULL,
            district TEXT,
            state TEXT,
            regen_score REAL NOT NULL,
            confidence_level TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_score_snapshots_farm
            ON score_snapshots(farm_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_score_snapshots_district
            ON score_snapshots(district, farm_id, created_at);
        """
    )
    # Upgrade path for a DB created before district/state existed - SQLite
    # has no "ADD COLUMN IF NOT EXISTS", so probe and add only if missing.
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(score_snapshots)")}
    if "district" not in existing_columns:
        conn.execute("ALTER TABLE score_snapshots ADD COLUMN district TEXT")
    if "state" not in existing_columns:
        conn.execute("ALTER TABLE score_snapshots ADD COLUMN state TEXT")


def init_db() -> None:
    """Explicit, idempotent - kept for main.py's startup lifespan; _connect() also self-initializes lazily (see above)."""
    with _connect():
        pass


def record_snapshot(
    farm_id: str,
    pincode: str,
    crop_name: str,
    regen_score: float,
    confidence_level: Optional[str],
    district: Optional[str] = None,
    state: Optional[str] = None,
) -> None:
    """Every completed /api/regenerate call logs one row - this IS the history, going forward."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO score_snapshots
                (farm_id, pincode, crop_name, district, state, regen_score, confidence_level, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (farm_id, pincode, crop_name, district, state, regen_score, confidence_level, int(time.time())),
        )


def get_district_peer_scores(district: str, exclude_farm_id: str, limit: int = 200) -> list[float]:
    """
    The MOST RECENT score for every OTHER farm_id in this district - one
    number per distinct farm, not per submission, so a single farm resubmitting
    repeatedly cannot skew the district's own peer average. Used by
    regeneration_score/peer_comparison.py; empty/short results there mean
    "not enough real nearby data yet" rather than a fabricated comparison.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT regen_score
            FROM score_snapshots
            WHERE district = ?
              AND farm_id != ?
              AND id IN (
                  SELECT MAX(id) FROM score_snapshots
                  WHERE district = ? AND farm_id != ?
                  GROUP BY farm_id
              )
            LIMIT ?
            """,
            (district, exclude_farm_id, district, exclude_farm_id, limit),
        ).fetchall()
    return [row["regen_score"] for row in rows]


def get_prior_snapshots(farm_id: str, limit: int = DEFAULT_HISTORY_LIMIT) -> list[sqlite3.Row]:
    """
    Snapshots for this farm_id, newest first, EXCLUDING the one just recorded
    by this same request (that's the current score, not "history" of it).
    Call this AFTER record_snapshot() for the current request.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT regen_score, confidence_level, created_at
            FROM score_snapshots
            WHERE farm_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (farm_id, limit + 1),
        ).fetchall()
    return list(rows[1:])
