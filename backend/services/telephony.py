"""
SMS/IVR fallback channel - a provider-agnostic gateway so a farmer without
a smartphone (or with no data connection) can still get a regeneration
score by plain SMS, the same way services/auth.py stays provider-agnostic
for phone-OTP login (see that module's FIREBASE_PROJECT_ID pattern - this
follows it).

TELEPHONY_PROVIDER controls what "sending an SMS" actually does:

  - "console" (default, no account needed) - the simulator. Appends to an
    in-memory OUTBOX and prints what would be sent, so the whole flow is
    real and testable (see smoke_test.py) without a paid account.
  - "twilio" - wires the real Twilio REST API. Needs TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER as env vars; the `twilio` package
    is imported lazily (only when this provider is selected) so it stays an
    optional dependency - see requirements.txt's note on it.

Swapping in a different real provider later (Exotel, Gupshup, etc.) means
adding one more branch in send_sms() - nothing else in this module, or any
caller of it, needs to change.

--------------------------------------------------------------------------
The SMS command format (deliberately terse - farmers type this on a T9
keypad, so it is positional, not a form):

    PIN CROP DAYS_SINCE_SOWING IRRIGATION [N P K PH OC]

    e.g. "141001 WHEAT 20 BOREWELL"
         "141001 WHEAT 20 BOREWELL 240 15 140 6.8 0.6"   (with a soil test)

Land size isn't asked for over SMS (there's no natural short way to type a
unit-aware area on a numeric keypad without a real risk of a farmer
mistyping the unit) - it defaults to 1 acre, which only affects the
absolute litres-of-water figure in module 5's irrigation advice, not the
regeneration score itself (every module downstream of the Feature Resolver
scores per-hectare rates, not the total). Documented here, not hidden.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Union

TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", "console").strip().lower()

# In-memory - the simulator's whole point is "no real account needed to see
# this work end-to-end". Cleared on process restart; a real provider branch
# doesn't touch this at all.
OUTBOX: list[dict[str, str]] = []

_IRRIGATION_ALIASES: dict[str, str] = {
    "RAINFED": "rainfed", "RAIN": "rainfed",
    "CANAL": "canal",
    "BOREWELL": "borewell", "BORE": "borewell",
    "TUBEWELL": "tubewell", "TUBE": "tubewell",
    "TANK_POND": "tank_pond", "TANK": "tank_pond", "POND": "tank_pond",
    "DRIP_SPRINKLER": "drip_sprinkler", "DRIP": "drip_sprinkler", "SPRINKLER": "drip_sprinkler",
    "OTHER": "other",
}


def send_sms(to_phone: str, message: str) -> None:
    """Provider-agnostic send. See module docstring for how TELEPHONY_PROVIDER picks the backend."""
    if TELEPHONY_PROVIDER == "twilio":
        _send_via_twilio(to_phone, message)
        return
    # Default: the console/local simulator.
    OUTBOX.append({"to": to_phone, "message": message})
    print(f"[telephony:console] SMS to {to_phone}: {message}")


def _send_via_twilio(to_phone: str, message: str) -> None:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.getenv("TWILIO_FROM_NUMBER", "").strip()
    if not (account_sid and auth_token and from_number):
        raise RuntimeError(
            "TELEPHONY_PROVIDER=twilio but TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / "
            "TWILIO_FROM_NUMBER aren't all set - see .env.example."
        )
    from twilio.rest import Client  # lazy import - optional dependency, see requirements.txt

    client = Client(account_sid, auth_token)
    client.messages.create(to=to_phone, from_=from_number, body=message)


# --------------------------------------------------------------------------
# Inbound command parsing
# --------------------------------------------------------------------------


@dataclass
class SmsFarmRequest:
    pincode: str
    crop_name: str
    sowing_date: date
    irrigation_source: str
    soil_test_available: bool
    soil_test_n_kg_per_ha: Optional[float] = None
    soil_test_p_kg_per_ha: Optional[float] = None
    soil_test_k_kg_per_ha: Optional[float] = None
    soil_test_ph: Optional[float] = None
    soil_test_organic_carbon_pct: Optional[float] = None


def parse_sms_command(text: str) -> Union[SmsFarmRequest, str]:
    """Returns a parsed SmsFarmRequest, or a plain-English error string (never raises) - an SMS reply is the only error channel a farmer on a feature phone has."""
    tokens = text.strip().split()
    if len(tokens) not in (4, 9):
        return (
            "Could not read that. Send: PIN CROP DAYS IRRIGATION "
            "e.g. 141001 WHEAT 20 BOREWELL (add N P K PH OC at the end if you have a soil test)."
        )

    pincode, crop_name, days_raw, irrigation_raw = tokens[:4]

    if not (pincode.isdigit() and len(pincode) == 6):
        return f"'{pincode}' is not a valid 6-digit PIN code."

    try:
        days_since_sowing = int(days_raw)
    except ValueError:
        return f"'{days_raw}' is not a number of days."
    if not (-365 <= days_since_sowing <= 365):
        return "Days since sowing must be between -365 and 365."

    irrigation_source = _IRRIGATION_ALIASES.get(irrigation_raw.upper())
    if irrigation_source is None:
        return f"'{irrigation_raw}' is not a known water source. Try RAINFED, CANAL, BOREWELL, TUBEWELL, TANK or DRIP."

    sowing_date = date.today() - timedelta(days=days_since_sowing)

    soil_values: list[Optional[float]] = [None] * 5
    if len(tokens) == 9:
        for i, raw in enumerate(tokens[4:9]):
            try:
                soil_values[i] = float(raw)
            except ValueError:
                return f"'{raw}' is not a valid soil test number."

    return SmsFarmRequest(
        pincode=pincode,
        crop_name=crop_name,
        sowing_date=sowing_date,
        irrigation_source=irrigation_source,
        soil_test_available=len(tokens) == 9,
        soil_test_n_kg_per_ha=soil_values[0],
        soil_test_p_kg_per_ha=soil_values[1],
        soil_test_k_kg_per_ha=soil_values[2],
        soil_test_ph=soil_values[3],
        soil_test_organic_carbon_pct=soil_values[4],
    )


def format_sms_reply(regen_score: Optional[float], confidence: Optional[str], weakest_module: Optional[str], improvement_tip: Optional[str]) -> str:
    """Compact, SMS-length summary of a /api/regenerate result - the inverse of the dashboard card, for a screen that doesn't exist."""
    if regen_score is None:
        return "KISAN MITRA: Not enough data for a score yet. Reply HELP for the message format."

    tip = (improvement_tip or "").strip()
    if len(tip) > 90:
        tip = tip[:87] + "..."

    parts = [f"KISAN MITRA: Regen score {regen_score}/100 ({confidence})."]
    if weakest_module:
        parts.append(f"Weakest: {weakest_module}.")
    if tip:
        parts.append(f"Tip: {tip}")
    return " ".join(parts)
