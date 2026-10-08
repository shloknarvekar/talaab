"""Name each pond after its nearest village (OpenStreetMap, ODbL), from a bundled places file.

backend/jobs/places/<name>.json is fetched once by scripts/fetch_places.py; nothing calls OSM
at run time. A pond keeps any place name the pipeline already gave it.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

PLACES_DIR = Path(__file__).resolve().parent / "places"
MAX_KM = 5.0


@lru_cache(maxsize=8)
def load_places(name: str) -> tuple[dict, ...]:
    path = PLACES_DIR / f"{name}.json"
    if not path.is_file():
        return ()
    return tuple(json.loads(path.read_text(encoding="utf-8"))["places"])


def places_for_region(region_id: str) -> tuple[dict, ...]:
    """latur-2024, latur-2026, latur-2024-synthetic -> places/latur.json"""
    return load_places(region_id.split("-")[0])


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def nearest(lat: float, lon: float, places, max_km: float = MAX_KM) -> dict | None:
    best, best_d = None, max_km
    for pl in places:
        d = distance_km(lat, lon, pl["lat"], pl["lon"])
        if d <= best_d:
            best, best_d = pl, d
    return best


def name_ponds(ponds: list[dict], places) -> int:
    """Fill place ("near X") and placeMr for ponds without a place. Returns how many were named."""
    named = 0
    for p in ponds:
        if (p.get("place") or "").strip():
            continue
        pl = nearest(p["lat"], p["lon"], places)
        if pl:
            p["place"] = f"near {pl['name']}"
            if pl.get("nameMr"):
                p["placeMr"] = pl["nameMr"]
            named += 1
    return named
