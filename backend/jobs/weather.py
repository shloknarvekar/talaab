"""Open-Meteo daily ET0 + rain for live regions (no API key; data CC BY 4.0, open-meteo.com).

One call to the forecast API returns recent past days and the next 16 days.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _get_json(url: str) -> dict:
    with urlopen(url, timeout=20) as r:  # noqa: S310 (fixed https URL)
        return json.loads(r.read())


def recent_and_forecast(lat: float, lon: float, today: date, past_days: int = 60,
                        get_json: Callable[[str], dict] = _get_json) -> tuple[list[dict], list[dict]]:
    """Return (observed up to today, forecast after today) as [{"date", "et0", "precip"}]."""
    q = urlencode({
        "latitude": lat, "longitude": lon,
        "daily": "et0_fao_evapotranspiration,precipitation_sum",
        "past_days": past_days, "forecast_days": 16, "timezone": "Asia/Kolkata",
    })
    daily = get_json(f"{FORECAST_URL}?{q}")["daily"]
    rows = [
        {"date": d, "et0": e, "precip": p}
        for d, e, p in zip(daily["time"], daily["et0_fao_evapotranspiration"], daily["precipitation_sum"])
        if e is not None
    ]
    t = today.isoformat()
    return [r for r in rows if r["date"] <= t], [r for r in rows if r["date"] > t]


def merge_observed(existing: list[dict], fetched: list[dict]) -> list[dict]:
    """Keep the pipeline's archive values; fill dates it does not have yet (archive lags a few days)."""
    by_date = {r["date"]: r for r in fetched}
    by_date.update({r["date"]: r for r in existing})
    return [by_date[d] for d in sorted(by_date)]
