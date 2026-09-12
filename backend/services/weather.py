"""
Weather + rainfall for a farm location.

STATUS: SYNTHETIC STUB. No network call is made. Numbers come from a coarse
month-of-year climatology for the Indian subcontinent, jittered by a seed
derived from (pincode, today) so that the same farm shows the same weather
all day - demos stay reproducible instead of flickering on every refresh.

TODO(integration): swap `get_weather()` for a real provider. Keep the
signature and the WeatherData return type and nothing downstream changes.
    * Open-Meteo   - free, no API key, has ET0 + 7-day forecast
    * IMD AgroMet  - official district-level agro advisories
    * NASA POWER   - long historical series, good for model training
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional

from models.schemas import LocationInfo, WeatherData, WeatherDay

# Very coarse all-India monthly climatology. Good enough to make the
# irrigation module behave sensibly across seasons; not good enough to
# advise a real farmer with. Hence the TODO above.
MONTHLY_RAIN_MM: dict[int, float] = {
    1: 15, 2: 14, 3: 12, 4: 10, 5: 28, 6: 150,
    7: 290, 8: 265, 9: 170, 10: 62, 11: 18, 12: 8,
}
MONTHLY_TMAX_C: dict[int, float] = {
    1: 23, 2: 26, 3: 32, 4: 37, 5: 40, 6: 36,
    7: 32, 8: 31, 9: 32, 10: 32, 11: 28, 12: 24,
}
MONTHLY_HUMIDITY_PCT: dict[int, float] = {
    1: 55, 2: 48, 3: 40, 4: 35, 5: 42, 6: 68,
    7: 82, 8: 84, 9: 76, 10: 62, 11: 56, 12: 58,
}


def _seeded_rng(pincode: str, today: date) -> random.Random:
    """Same farm + same day -> same weather. Demos should not flicker."""
    return random.Random(f"{pincode}|{today.isoformat()}")


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


def _et0_for(month: int, temp_max_c: float, humidity_pct: float) -> float:
    """
    Crude reference-evapotranspiration proxy (mm/day).

    TODO(agronomy): replace with proper FAO-56 Penman-Monteith once we have
    real radiation and wind data from the weather provider.
    """
    et0 = 0.16 * temp_max_c - 0.03 * humidity_pct + 1.4
    if month in (6, 7, 8, 9):  # monsoon cloud cover suppresses demand
        et0 -= 0.6
    return round(max(1.5, min(9.0, et0)), 2)


def get_weather(
    location: LocationInfo,
    on_date: Optional[date] = None,
) -> WeatherData:
    """Current + 7-day-forecast weather for the farm's location."""
    today = on_date or date.today()
    rng = _seeded_rng(location.pincode, today)
    month = today.month

    base_rain = MONTHLY_RAIN_MM[month]
    base_tmax = MONTHLY_TMAX_C[month]
    base_humidity = MONTHLY_HUMIDITY_PCT[month]

    # A dry district and a wet one in the same month should not look identical.
    regional_factor = 0.6 + rng.random() * 0.8

    temp_max_c = round(base_tmax + rng.uniform(-3.0, 3.0), 1)
    temp_min_c = round(temp_max_c - rng.uniform(9.0, 14.0), 1)
    humidity_pct = round(min(98.0, max(15.0, base_humidity + rng.uniform(-8.0, 8.0))), 1)

    rainfall_last_7d = round(max(0.0, base_rain / 30 * 7 * regional_factor * rng.uniform(0.4, 1.6)), 1)
    rainfall_last_30d = round(max(0.0, base_rain * regional_factor * rng.uniform(0.7, 1.3)), 1)

    forecast: list[WeatherDay] = []
    forecast_total = 0.0
    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        # Rain is bursty: most days dry, occasional heavy day.
        rains = rng.random() < min(0.75, base_rain / 300 + 0.06)
        rain_mm = round(rng.uniform(1.0, base_rain / 6 + 4) * regional_factor, 1) if rains else 0.0
        forecast_total += rain_mm
        day_tmax = round(temp_max_c + rng.uniform(-2.5, 2.5) - (2.5 if rain_mm > 10 else 0), 1)
        forecast.append(
            WeatherDay(
                date=day.isoformat(),
                rain_mm=rain_mm,
                temp_max_c=day_tmax,
                temp_min_c=round(day_tmax - rng.uniform(9.0, 13.0), 1),
                condition=_condition(rain_mm),
            )
        )

    return WeatherData(
        source="synthetic-stub (climatology + seeded jitter)",
        latitude=location.latitude,
        longitude=location.longitude,
        temp_max_c=temp_max_c,
        temp_min_c=temp_min_c,
        humidity_pct=humidity_pct,
        rainfall_last_7d_mm=rainfall_last_7d,
        rainfall_last_30d_mm=rainfall_last_30d,
        rainfall_forecast_7d_mm=round(forecast_total, 1),
        et0_mm_per_day=_et0_for(month, temp_max_c, humidity_pct),
        forecast=forecast,
    )
