"""
Real phone-OTP login + family members - see MASTER PROMPT STEP 4/"STOP AND ASK"
answers: Firebase Phone Auth on the client, SQLite here on the backend.

Flow:
  1. Frontend uses Firebase Phone Auth to send/verify an SMS OTP and gets a
     Firebase ID token back.
  2. Frontend POSTs that ID token to /api/auth/verify (see main.py).
  3. `verify_firebase_id_token()` below checks it against Google's public
     certs using only FIREBASE_PROJECT_ID - no service-account file needed.
  4. We upsert a `users` row keyed by the token's Firebase uid, mint our own
     opaque session token, and hand that back. Every other authenticated
     endpoint (family members) takes that token as `Authorization: Bearer`.

Until FIREBASE_PROJECT_ID is set, `verify_firebase_id_token` raises
AuthNotConfiguredError - callers turn that into a clear 503, not a silent
fake login.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.sqlite3"
SESSION_LIFETIME_SECONDS = 30 * 24 * 60 * 60  # 30 days

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()

_google_request = google_requests.Request()


class AuthNotConfiguredError(RuntimeError):
    """Raised when FIREBASE_PROJECT_ID isn't set - not a login failure, a setup gap."""


class InvalidTokenError(RuntimeError):
    """The Firebase ID token failed verification (expired, wrong project, tampered)."""


@dataclass
class VerifiedFirebaseUser:
    uid: str
    phone: str


def verify_firebase_id_token(id_token_str: str) -> VerifiedFirebaseUser:
    if not FIREBASE_PROJECT_ID:
        raise AuthNotConfiguredError(
            "FIREBASE_PROJECT_ID is not set - see .env.local.example. "
            "Login is fully built but needs a Firebase project to verify against."
        )
    try:
        claims = google_id_token.verify_firebase_token(
            id_token_str, _google_request, audience=FIREBASE_PROJECT_ID
        )
    except ValueError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if not claims or "phone_number" not in claims:
        raise InvalidTokenError("Token has no phone_number claim - was Phone Auth used?")

    return VerifiedFirebaseUser(uid=claims["sub"], phone=claims["phone_number"])


# --------------------------------------------------------------------------
# SQLite - a single file, zero external services (see MASTER PROMPT's
# persistence-layer answer). Fine for a farmer-count in the hundreds/low
# thousands; swap for a hosted DB later by replacing just this module.
# --------------------------------------------------------------------------


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                firebase_uid TEXT UNIQUE NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS family_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                phone TEXT,
                created_at INTEGER NOT NULL
            );
            """
        )


def upsert_user_and_create_session(firebase_user: VerifiedFirebaseUser) -> str:
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO users (firebase_uid, phone, created_at) VALUES (?, ?, ?)
            ON CONFLICT(firebase_uid) DO UPDATE SET phone = excluded.phone
            """,
            (firebase_user.uid, firebase_user.phone, now),
        )
        user_id = conn.execute(
            "SELECT id FROM users WHERE firebase_uid = ?", (firebase_user.uid,)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now, now + SESSION_LIFETIME_SECONDS),
        )
    return token


@dataclass
class SessionUser:
    user_id: int
    phone: str


def get_session_user(token: str) -> Optional[SessionUser]:
    now = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT u.id AS user_id, u.phone AS phone, s.expires_at AS expires_at
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if row is None or row["expires_at"] < now:
        return None
    return SessionUser(user_id=row["user_id"], phone=row["phone"])


def delete_session(token: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# --------------------------------------------------------------------------
# Family members
# --------------------------------------------------------------------------


def list_family_members(user_id: int) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT id, name, phone, created_at FROM family_members WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()


def add_family_member(user_id: int, name: str, phone: Optional[str]) -> sqlite3.Row:
    now = int(time.time())
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO family_members (user_id, name, phone, created_at) VALUES (?, ?, ?, ?)",
            (user_id, name, phone, now),
        )
        member_id = cursor.lastrowid
        return conn.execute(
            "SELECT id, name, phone, created_at FROM family_members WHERE id = ?",
            (member_id,),
        ).fetchone()


def remove_family_member(user_id: int, member_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM family_members WHERE id = ? AND user_id = ?",
            (member_id, user_id),
        )
        return cursor.rowcount > 0
