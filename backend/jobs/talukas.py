"""Tag each pond with its taluka (tehsil), from bundled OpenStreetMap boundaries (ODbL).

Drought is declared per taluka and district plans are made per taluka, so every pond carries the
one it lies in. backend/jobs/places/<name>-talukas.json is fetched once by scripts/fetch_talukas.py;
nothing calls OSM at run time. A pond just outside every outline (the outlines are simplified to
~50 m) goes to the nearest taluka within MAX_EDGE_KM; farther than that it gets none.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

PLACES_DIR = Path(__file__).resolve().parent / "places"
MAX_EDGE_KM = 2.0


@lru_cache(maxsize=8)
def load_talukas(name: str) -> tuple[dict, ...]:
    path = PLACES_DIR / f"{name}-talukas.json"
    if not path.is_file():
        return ()
    return tuple(json.loads(path.read_text(encoding="utf-8"))["talukas"])


def talukas_for_region(region_id: str) -> tuple[dict, ...]:
    """latur-2024, latur-district-2026, ... -> places/latur-talukas.json"""
    return load_talukas(region_id.split("-")[0])


def _polygons(geometry: dict) -> list:
    return [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]


def _in_ring(lon: float, lat: float, ring: list) -> bool:
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi, xj, yj = ring[i][0], ring[i][1], ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def contains(geometry: dict, lon: float, lat: float) -> bool:
    return any(_in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, hole) for hole in poly[1:])
               for poly in _polygons(geometry))


def _edge_km(geometry: dict, lon: float, lat: float) -> float:
    """Distance from the point to the nearest boundary segment (local equirectangular, fine at 2 km)."""
    kx, ky = 111.32 * math.cos(math.radians(lat)), 110.57
    best = math.inf
    for poly in _polygons(geometry):
        for ring in poly:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                ax, ay, bx, by = (x1 - lon) * kx, (y1 - lat) * ky, (x2 - lon) * kx, (y2 - lat) * ky
                dx, dy = bx - ax, by - ay
                t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
                best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def taluka_of(lat: float, lon: float, talukas) -> dict | None:
    candidates = [t for t in talukas if t["bbox"][0] <= lon <= t["bbox"][2] and t["bbox"][1] <= lat <= t["bbox"][3]]
    for t in candidates:
        if contains(t["geometry"], lon, lat):
            return t
    near = min(((_edge_km(t["geometry"], lon, lat), t) for t in talukas), default=None, key=lambda x: x[0])
    return near[1] if near and near[0] <= MAX_EDGE_KM else None


def tag_ponds(ponds: list[dict], talukas) -> int:
    """Set taluka (+ talukaMr) on every pond inside a known taluka. Returns how many were tagged."""
    tagged = 0
    for p in ponds:
        t = taluka_of(p["lat"], p["lon"], talukas) if talukas else None
        if t:
            p["taluka"] = t["name"]
            if t.get("nameMr"):
                p["talukaMr"] = t["nameMr"]
            tagged += 1
    return tagged
