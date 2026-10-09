"""District-scale processing helpers: boundary, grid of cells, point-in-district.

A district is split into cells of CELL_DEG (0.15 deg, the size of the box Talaab was validated
on). Each cell is processed independently (on AWS Lambda, in parallel) over its bbox *plus* an
OVERLAP margin, so a pond cut by a cell edge is still seen whole; a pond is kept only by the cell
whose CORE contains its centroid, which removes duplicates without any matching.

Boundary: OpenStreetMap (c) OpenStreetMap contributors, ODbL (fetched once, committed).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List

BOUNDARIES = Path(__file__).resolve().parent / "boundaries"
CELL_DEG = 0.15
OVERLAP_DEG = 0.015  # ~1.6 km: wider than any 200 ha pond is long


def load_boundary(name: str) -> dict:
    return json.loads((BOUNDARIES / f"{name}.json").read_text(encoding="utf-8"))


def _rings(geometry: dict) -> List[List[List[List[float]]]]:
    """Polygons as [ [outer, hole, ...], ... ] regardless of Polygon / MultiPolygon."""
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    raise ValueError(f"unsupported geometry {geometry['type']}")


def _in_ring(lon: float, lat: float, ring: List[List[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def contains(geometry: dict, lon: float, lat: float) -> bool:
    for poly in _rings(geometry):
        if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, hole) for hole in poly[1:]):
            return True
    return False


def area_km2(geometry: dict) -> float:
    """Planar area on a local equirectangular projection (fine at district scale)."""
    total = 0.0
    for poly in _rings(geometry):
        for k, ring in enumerate(poly):
            lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
            pts = [(math.radians(p[0]) * 6371.0 * math.cos(lat0), math.radians(p[1]) * 6371.0) for p in ring]
            a = 0.5 * abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])))
            total += a if k == 0 else -a
    return total


def _cell_touches(geometry: dict, w: float, s: float, e: float, n: float, samples: int = 6) -> bool:
    """Cheap test: any sample point of the cell lies in the district, or any boundary vertex lies in the cell."""
    for i in range(samples + 1):
        for j in range(samples + 1):
            if contains(geometry, w + (e - w) * i / samples, s + (n - s) * j / samples):
                return True
    return any(w <= p[0] <= e and s <= p[1] <= n for poly in _rings(geometry) for ring in poly for p in ring)


def grid_cells(boundary: dict, cell_deg: float = CELL_DEG, overlap_deg: float = OVERLAP_DEG) -> List[dict]:
    """Cells covering the district: {id, core: [W,S,E,N], bbox: core + overlap}."""
    w0, s0, e0, n0 = boundary["bbox"]
    geometry = boundary["geometry"]
    cells = []
    cols = math.ceil((e0 - w0) / cell_deg)
    rows = math.ceil((n0 - s0) / cell_deg)
    for r in range(rows):
        for c in range(cols):
            w, s = w0 + c * cell_deg, s0 + r * cell_deg
            e, n = min(w + cell_deg, e0), min(s + cell_deg, n0)
            if not _cell_touches(geometry, w, s, e, n):
                continue
            core = [round(w, 5), round(s, 5), round(e, 5), round(n, 5)]
            bbox = [round(w - overlap_deg, 5), round(s - overlap_deg, 5), round(e + overlap_deg, 5), round(n + overlap_deg, 5)]
            cells.append({"id": f"c{r:02d}-{c:02d}", "core": core, "bbox": bbox})
    return cells


def in_core(core: List[float], lon: float, lat: float) -> bool:
    """Half-open, so a centroid exactly on a shared edge belongs to exactly one cell."""
    w, s, e, n = core
    return w <= lon < e and s <= lat < n


def merge_cells(cells: List[dict], geometry: dict) -> tuple:
    """Cell outputs -> (district scenes, district ponds).

    Keeps ponds whose centre is inside the district. Every district pass gets one scene, and every
    pond gets one history entry per pass: a pass a cell did not see counts as invalid (not observed),
    never as 0 ha of water.
    """
    scenes_by_date: dict = {}
    ponds: List[dict] = []
    for c in cells:
        for s in c["scenes"]:
            scenes_by_date.setdefault(s["date"], {"date": s["date"], "id": s["id"], "status": "ok"})
        ponds += [dict(p) for p in c["ponds"] if contains(geometry, p["lon"], p["lat"])]
    for p in ponds:
        have = {h["date"] for h in p["history"]}
        p["history"] = sorted(p["history"] + [{"date": d, "areaHa": 0.0, "valid": False} for d in scenes_by_date if d not in have],
                              key=lambda h: h["date"])
    return [scenes_by_date[d] for d in sorted(scenes_by_date)], ponds
