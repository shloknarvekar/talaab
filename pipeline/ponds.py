"""Pond detection and measurement module.

Finds connected water components on reference scene, creates 2-px dilated footprints,
resolves nearest places from OSM, and measures water area per scene pass.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import numpy as np
import scipy.ndimage as ndi
from rasterio.warp import transform

PLACES_JSON_PATH = Path(__file__).resolve().parents[1] / "backend" / "jobs" / "places" / "latur.json"


@dataclass
class DetectedPond:
    id: str
    lat: float
    lon: float
    place: str
    place_mr: str | None
    ref_area_ha: float
    footprint_mask: np.ndarray  # 2D boolean array matching scene shape

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "lat": round(float(self.lat), 4),
            "lon": round(float(self.lon), 4),
            "place": self.place,
            "refAreaHa": round(float(self.ref_area_ha), 2),
        }
        if self.place_mr:
            d["placeMr"] = self.place_mr
        return d


@dataclass
class PondMeasurement:
    date: str
    area_ha: float
    valid: bool

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "areaHa": round(float(self.area_ha), 2),
            "valid": bool(self.valid),
        }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points."""
    r = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def load_places(places_path: Path = PLACES_JSON_PATH) -> list[dict]:
    """Load village/place locations from JSON file if available."""
    if not places_path.exists():
        return []
    try:
        data = json.loads(places_path.read_text(encoding="utf-8"))
        return data.get("places", [])
    except Exception:
        return []


def find_nearest_place(lat: float, lon: float, places: list[dict], max_dist_km: float = 5.0) -> Tuple[str, str | None]:
    """Return place name string ("near <village>") and optional Marathi name."""
    if not places:
        return "", None

    best_place = None
    best_dist = float("inf")

    for p in places:
        plat, plon = p.get("lat"), p.get("lon")
        if plat is None or plon is None:
            continue
        dist = _haversine_km(lat, lon, plat, plon)
        if dist < best_dist:
            best_dist = dist
            best_place = p

    if best_place and best_dist <= max_dist_km:
        name = best_place.get("name", "")
        name_mr = best_place.get("nameMr")
        return f"near {name}" if name else "", name_mr

    return "", None


def detect_ponds(
    water_mask: np.ndarray,
    scl_invalid_mask: np.ndarray,
    transform_affine,
    crs,
    min_ha: float = 1.0,
    max_ha: float = 200.0,
    pixel_area_ha: float = 0.01,
    places_path: Path = PLACES_JSON_PATH,
) -> List[DetectedPond]:
    """Detect ponds from water mask on reference scene.

    Filter connected components to 1-200 ha (100 to 20,000 pixels at 10m).
    Dilate footprint by 2 pixels. Sort ponds by area descending, assign P001, P002...
    """
    valid_water = water_mask & (~scl_invalid_mask)
    labeled, num_features = ndi.label(valid_water)

    min_px = int(math.ceil(min_ha / pixel_area_ha))
    max_px = int(math.floor(max_ha / pixel_area_ha))

    places = load_places(places_path)
    raw_ponds = []

    for label_idx in range(1, num_features + 1):
        comp_mask = labeled == label_idx
        px_count = np.sum(comp_mask)

        if not (min_px <= px_count <= max_px):
            continue

        ref_area = px_count * pixel_area_ha

        # Footprint dilated by 2 pixels
        footprint = ndi.binary_dilation(comp_mask, iterations=2)

        # Centroid calculation in pixel coordinates
        y_indices, x_indices = np.where(comp_mask)
        y_center = float(np.mean(y_indices))
        x_center = float(np.mean(x_indices))

        # Convert pixel coordinates to UTM x, y
        x_utm, y_utm = transform_affine * (x_center + 0.5, y_center + 0.5)

        # Convert UTM coordinates to WGS84 lat, lon
        lons, lats = transform(crs, "EPSG:4326", [x_utm], [y_utm])
        lat, lon = lats[0], lons[0]

        place_str, place_mr = find_nearest_place(lat, lon, places)

        raw_ponds.append({
            "lat": lat,
            "lon": lon,
            "place": place_str,
            "place_mr": place_mr,
            "ref_area_ha": ref_area,
            "footprint_mask": footprint,
        })

    # Sort ponds largest first by ref_area_ha
    raw_ponds.sort(key=lambda p: p["ref_area_ha"], reverse=True)

    # Assign IDs P001, P002, ...
    detected_ponds = []
    for idx, p in enumerate(raw_ponds, start=1):
        pond_id = f"P{idx:03d}"
        pond = DetectedPond(
            id=pond_id,
            lat=p["lat"],
            lon=p["lon"],
            place=p["place"],
            place_mr=p["place_mr"],
            ref_area_ha=p["ref_area_ha"],
            footprint_mask=p["footprint_mask"],
        )
        detected_ponds.append(pond)

    return detected_ponds


def measure_pond_pass(
    pond: DetectedPond,
    water_mask: np.ndarray,
    scl_invalid_mask: np.ndarray,
    date_str: str,
    pixel_area_ha: float = 0.01,
) -> PondMeasurement:
    """Measure pond water area for a single pass.

    If >20% of footprint is cloud/shadow/no-data, mark valid=False.
    """
    footprint = pond.footprint_mask
    total_fp_pixels = np.sum(footprint)

    if total_fp_pixels == 0:
        return PondMeasurement(date=date_str, area_ha=0.0, valid=False)

    invalid_fp_pixels = np.sum(footprint & scl_invalid_mask)
    invalid_ratio = invalid_fp_pixels / float(total_fp_pixels)

    valid = invalid_ratio <= 0.20

    # Count valid water pixels inside footprint
    water_pixels = np.sum(footprint & water_mask & (~scl_invalid_mask))
    area_ha = water_pixels * pixel_area_ha

    return PondMeasurement(
        date=date_str,
        area_ha=round(float(area_ha), 2),
        valid=valid,
    )
