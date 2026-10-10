"""Build the division map: one light outline per district, from the district boundaries, once.

    python backend/scripts/build_division_outlines.py [--division marathwada-2026]

Reads pipeline/boundaries/<slug>-district.json (scripts/fetch_districts.py) for every member of the division
and writes backend/jobs/places/<division>-districts.geojson, served by GET /division/outlines. The outlines
are simplified (Douglas-Peucker, ~300 m) so the whole division is a few tens of KB: good for a map of
districts, not for measuring. Data (c) OpenStreetMap contributors, ODbL.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from jobs.regions import DISTRICT_MR, DIVISIONS, district_name, division_members  # noqa: E402

BOUNDARIES = ROOT / "pipeline" / "boundaries"
OUT_DIR = ROOT / "backend" / "jobs" / "places"
TOLERANCE_DEG = 0.003  # ~300 m: district shapes stay recognisable at division zoom
DECIMALS = 4           # ~10 m


def _perp(p, a, b):
    """Distance from p to segment a-b (degrees; fine for simplification at this scale)."""
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return ((x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2) ** 0.5


def simplify(points: list, tol: float) -> list:
    """Douglas-Peucker without recursion (rings have thousands of points)."""
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        best, k = 0.0, None
        for m in range(i + 1, j):
            d = _perp(points[m], points[i], points[j])
            if d > best:
                best, k = d, m
        if k is not None and best > tol:
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [p for p, kept in zip(points, keep) if kept]


def ring(coords: list) -> list | None:
    out = [[round(x, DECIMALS), round(y, DECIMALS)] for x, y in simplify(coords, TOLERANCE_DEG)]
    if out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else None  # a valid closed ring; tiny slivers vanish


def polygons(geometry: dict) -> list:
    polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    out = []
    for poly in polys:
        outer = ring(poly[0])
        if outer:  # keep a polygon only if its outer ring survives; holes too small to see are dropped
            out.append([outer] + [r for r in (ring(c) for c in poly[1:]) if r])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--division", default="marathwada-2026", choices=sorted(DIVISIONS))
    args = ap.parse_args()
    features = []
    for region in division_members(args.division):
        slug = region.split("-district-")[0]
        src = json.loads((BOUNDARIES / f"{slug}-district.json").read_text(encoding="utf-8"))
        polys = polygons(src["geometry"])
        name = district_name(region)
        geometry = {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else {"type": "MultiPolygon", "coordinates": polys}
        features.append({"type": "Feature", "properties": {"region": region, "name": name, "nameMr": DISTRICT_MR.get(name)},
                         "geometry": geometry})
        print(f"{region}: {sum(len(r) for p in polys for r in p)} points")
    doc = {"type": "FeatureCollection", "division": args.division,
           "credit": "District boundaries (c) OpenStreetMap contributors, ODbL", "features": features}
    out = OUT_DIR / f"{args.division}-districts.geojson"
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB, {len(features)} districts)")


if __name__ == "__main__":
    main()
