"""
Weather + rainfall for a farm location.

STATUS: LIVE. Calls Open-Meteo (https://open-meteo.com) - free, no API key,
one request returns 30 days of history + today + 7-day forecast in a
single call (`past_days=30&forecast_days=7`), including FAO-56 reference
evapotranspiration (et0_fao_evapotranspiration) directly - no separate
Penman-Monteith calc needed. This was the exact provider the original
synthetic-stub docstring named as the intended swap-in; the WeatherData
return shape is unchanged, so nothing downstream (M3, M5, M2's trend) had
to change.

Graceful degradation, unchanged from the stub it replaced: if coordinates
are unresolved (no PIN match, no GPS) or the API call fails/times out,
this raises - aggregator.py already catches that and records "weather" as
a data_gap rather than crashing the whole request. A short in-process
cache (by rounded lat/lon) avoids hammering the API for repeat requests
against the same farm within a demo session.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any, Optional

from models.schemas import LocationInfo, WeatherData, WeatherDay

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 8
CACHE_TTL_SECONDS = 3600  # 1 hour - weather doesn't need per-second freshness for advisory purposes

PAST_DAYS = 30
# Open-Meteo's forecast_days INCLUDES today (forecast_days=7 -> today + 6
# more days). Requesting 8 gives today + 7 full days strictly after today,
# matching the original stub's semantic (forecast = the next 7 days, not
# including today, which is reported separately as the "current" fields).
FORECAST_DAYS_REQUEST = 8
FORECAST_DAYS = 7

_CACHE: dict[tuple[float, float], tuple[float, WeatherData]] = {}


def _condition(rain_mm: float) -> str:
    if rain_mm >= 25:
        return "Heavy rain"
    if rain_mm >= 7.5:
        return "Moderate rain"
    if rain_mm >= 1:
        return "Light rain"
    if rain_mm > 0:
        return "Cloudy"
    return "Clear"


def _fetch_open_meteo(lat: float, lon: float) -> dict[str, Any]:
    params = {
        "latitude": round(lat, 3),
        "longitude": round(lon, 3),
        "daily": (
            "temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,"
            "precipitation_sum,et0_fao_evapotranspiration"
        ),
        "timezone": "Asia/Kolkata",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS_REQUEST,
    }
    url = f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "kisan-sathi/1.0"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read())


def _safe_sum(values: list[Optional[float]]) -> float:
    return round(sum(v for v in values if v is not None), 1)


def get_weather(
    location: LocationInfo,
    on_date: Optional[date] = None,
) -> WeatherData:
    """Live current + 7-day-forecast weather for the farm's location, via Open-Meteo."""
    today = on_date or date.today()

    if location.latitude is None or location.longitude is None:
        raise ValueError("No coordinates resolved for this location - cannot fetch live weather.")

    cache_key = (round(location.latitude, 2), round(location.longitude, 2))
    cached = _CACHE.get(cache_key)
    if cached is not None and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
        return cached[1]

    try:
        raw = _fetch_open_meteo(location.latitude, location.longitude)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Open-Meteo request failed: {type(exc).__name__}: {exc}") from exc

    daily = raw.get("daily")
    if not daily or "time" not in daily:
        raise RuntimeError(f"Open-Meteo returned an unexpected shape: {raw}")

    dates: list[str] = daily["time"]
    today_str = today.isoformat()
    # Open-Meteo returns exactly PAST_DAYS + 1 (today) + FORECAST_DAYS entries,
    # with "today" at a fixed offset from the end - used as a fallback if the
    # exact date string isn't found (e.g. a synthetic `on_date` in a test).
    today_idx = dates.index(today_str) if today_str in dates else max(0, len(dates) - FORECAST_DAYS_REQUEST)

    precip = daily["precipitation_sum"]
    tmax = daily["temperature_2m_max"]
    tmin = daily["temperature_2m_min"]
    humidity = daily["relative_humidity_2m_mean"]
    et0 = daily["et0_fao_evapotranspiration"]

    rainfall_last_7d = _safe_sum(precip[max(0, today_idx - 7) : today_idx])
    rainfall_last_30d = _safe_sum(precip[max(0, today_idx - 30) : today_idx])

    forecast_indices = list(range(today_idx + 1, min(len(dates), today_idx + 1 + FORECAST_DAYS)))
    rainfall_forecast_7d = _safe_sum([precip[i] for i in forecast_indices])

    forecast: list[WeatherDay] = []
    for i in forecast_indices:
        rain_mm = round(precip[i] or 0.0, 1)
        forecast.append(
            WeatherDay(
                date=dates[i],
                rain_mm=rain_mm,
                temp_max_c=round(tmax[i], 1) if tmax[i] is not None else 0.0,
                temp_min_c=round(tmin[i], 1) if tmin[i] is not None else 0.0,
                condition=_condition(rain_mm),
            )
        )

    today_et0 = et0[today_idx] if today_idx < len(et0) and et0[today_idx] is not None else 4.0
    today_tmax = tmax[today_idx] if tmax[today_idx] is not None else 30.0
    today_tmin = tmin[today_idx] if tmin[today_idx] is not None else 20.0
    today_humidity = humidity[today_idx] if humidity[today_idx] is not None else 55.0

    result = WeatherData(
        source="Open-Meteo (live)",
        latitude=location.latitude,
        longitude=location.longitude,
        temp_max_c=round(today_tmax, 1),
        temp_min_c=round(today_tmin, 1),
        humidity_pct=round(today_humidity, 1),
        rainfall_last_7d_mm=rainfall_last_7d,
        rainfall_last_30d_mm=rainfall_last_30d,
        rainfall_forecast_7d_mm=rainfall_forecast_7d,
        et0_mm_per_day=round(today_et0, 2),
        forecast=forecast,
    )
    _CACHE[cache_key] = (time.time(), result)
    return result


def clear_cache() -> None:
    """Force the next call to re-fetch from Open-Meteo. Handy in tests."""
    _CACHE.clear()
