"""Evaporation and weather data module.

Fetches daily ET0 evapotranspiration and precipitation from Open-Meteo archive API,
and computes 2019-2023 climatology averages per calendar day (MM-DD).

Data credits: Open-Meteo.com (CC BY 4.0).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
import requests

DEFAULT_LAT = 18.41
DEFAULT_LON = 76.55
ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / ".cache"


def fetch_daily_weather(
    start_date: str,
    end_date: str,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    use_cache: bool = True,
) -> List[dict]:
    """Fetch daily ET0 (mm/day) and precipitation (mm) from Open-Meteo archive API.

    Returns list of dicts: [{"date": "YYYY-MM-DD", "et0": float, "precip": float}]
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"weather_{lat}_{lon}_{start_date}_{end_date}.json"

    if use_cache and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ["et0_fao_evapotranspiration", "precipitation_sum"],
        "timezone": "auto",
    }

    response = requests.get(ARCHIVE_API_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    daily = data.get("daily", {})
    times = daily.get("time", [])
    et0_vals = daily.get("et0_fao_evapotranspiration", [])
    precip_vals = daily.get("precipitation_sum", [])

    results = []
    for t, et, pr in zip(times, et0_vals, precip_vals):
        et_clean = round(float(et), 2) if et is not None else 0.0
        pr_clean = round(float(pr), 2) if pr is not None else 0.0
        results.append({
            "date": t,
            "et0": et_clean,
            "precip": pr_clean,
        })

    if use_cache:
        try:
            cache_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
        except Exception:
            pass

    return results


def fetch_climatology_2019_2023(
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    use_cache: bool = True,
) -> Dict[str, float]:
    """Fetch 2019-2023 daily ET0 and compute mean ET0 (mm/day) for each calendar day 'MM-DD'.

    Returns dict mapping "MM-DD" -> mean ET0 rounded to 2 decimal places.
    Ensures all 365 or 366 MM-DD keys are present.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"climatology_2019_2023_{lat}_{lon}.json"

    if use_cache and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2019-01-01",
        "end_date": "2023-12-31",
        "daily": ["et0_fao_evapotranspiration"],
        "timezone": "auto",
    }

    response = requests.get(ARCHIVE_API_URL, params=params, timeout=20)
    response.raise_for_status()
    daily = response.json().get("daily", {})

    times = daily.get("time", [])
    et0_vals = daily.get("et0_fao_evapotranspiration", [])

    by_mmdd = defaultdict(list)
    for t, et in zip(times, et0_vals):
        if et is not None:
            mmdd = t[5:]  # Extract "MM-DD"
            by_mmdd[mmdd].append(float(et))

    climatology = {}
    for mmdd, vals in by_mmdd.items():
        if vals:
            climatology[mmdd] = round(sum(vals) / len(vals), 2)

    # Ensure 02-29 is present if leap year missing
    if "02-29" not in climatology and "02-28" in climatology and "03-01" in climatology:
        climatology["02-29"] = round((climatology["02-28"] + climatology["03-01"]) / 2.0, 2)

    if use_cache:
        try:
            cache_file.write_text(json.dumps(climatology, indent=2), encoding="utf-8")
        except Exception:
            pass

    return climatology
