"""Process one district grid cell: find its ponds and measure them on every pass.

Differences from the single-box path (run_replay.py), needed at district scale:
- a district spans several Sentinel-2 tiles, so for each date the image covering the cell best is used;
- every band is read onto ONE fixed 10 m grid per cell (snapped UTM bounds, boundless reads), so pond
  footprints line up across dates even when the source tile changes;
- only ponds whose centroid lies in the cell's core are returned (neighbours own the rest).
Reuses Nikhil's NDWI, SCL masking, pond detection and measurement code unchanged.

Data credits: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search).
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform_bounds

from pipeline.district import in_core
from pipeline.ponds import detect_ponds, measure_pond_pass
from pipeline.water import DEFAULT_INVALID_SCL, DEFAULT_NDWI_THRESHOLD, compute_ndwi, get_scl_invalid_mask

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
PIXEL_M = 10.0
REFERENCE_WINDOW_DAYS = 15


def _overlap(a, b) -> float:
    """Fraction of bbox b covered by bbox a (lon/lat)."""
    w, s, e, n = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    if e <= w or n <= s:
        return 0.0
    return (e - w) * (n - s) / ((b[2] - b[0]) * (b[3] - b[1]))


def best_items_by_date(bbox, start: str, end: str, max_cloud: float) -> list[dict]:
    """One item per date: the one covering the cell best, then the least cloudy."""
    search = pystac_client.Client.open(EARTH_SEARCH).search(
        collections=["sentinel-2-l2a"], bbox=bbox, datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": max_cloud}})
    best: dict[str, dict] = {}
    for item in search.items():
        assets = item.assets
        if not all(k in assets for k in ("green", "nir", "scl")):
            continue
        cand = {"date": item.datetime.date().isoformat(), "id": item.id, "coverage": round(_overlap(item.bbox, bbox), 3),
                "cloud": float(item.properties.get("eo:cloud_cover", 100)), "epsg": item.properties.get("proj:epsg"),
                "green": assets["green"].href, "nir": assets["nir"].href, "scl": assets["scl"].href,
                "visual": assets["visual"].href if "visual" in assets else None}
        cur = best.get(cand["date"])
        if cur is None or (cand["coverage"], -cand["cloud"]) > (cur["coverage"], -cur["cloud"]):
            best[cand["date"]] = cand
    return [best[d] for d in sorted(best)]


def fixed_grid(bbox, crs: str):
    """Snapped UTM bounds, shape and affine transform for the cell (identical for every date)."""
    left, bottom, right, top = transform_bounds("EPSG:4326", crs, *bbox)
    left, bottom = math.floor(left / PIXEL_M) * PIXEL_M, math.floor(bottom / PIXEL_M) * PIXEL_M
    right, top = math.ceil(right / PIXEL_M) * PIXEL_M, math.ceil(top / PIXEL_M) * PIXEL_M
    shape = (int(round((top - bottom) / PIXEL_M)), int(round((right - left) / PIXEL_M)))
    return (left, bottom, right, top), shape, Affine(PIXEL_M, 0, left, 0, -PIXEL_M, top)


def _read(url: str, bounds, shape, resampling) -> np.ndarray:
    with rasterio.open(url) as src:
        window = rasterio.windows.from_bounds(*bounds, transform=src.transform)
        return src.read(1, window=window, out_shape=shape, boundless=True, fill_value=0, resampling=resampling)


def read_masks(item: dict, bounds, shape, ndwi_threshold: float = DEFAULT_NDWI_THRESHOLD):
    green = _read(item["green"], bounds, shape, Resampling.bilinear).astype(np.float32)
    nir = _read(item["nir"], bounds, shape, Resampling.bilinear).astype(np.float32)
    scl = _read(item["scl"], bounds, shape, Resampling.nearest)
    invalid = get_scl_invalid_mask(scl, DEFAULT_INVALID_SCL) | (green <= 0) | (nir <= 0)
    water = (compute_ndwi(green, nir) > ndwi_threshold) & ~invalid
    return water, invalid


import logging


def process_cell(
    cell: dict,
    start: str,
    end: str,
    reference_date: str,
    max_cloud: float = 20.0,
    region_id: str | None = None,
    bucket: str | None = None,
    s3_client=None,
    output_dir=None,
) -> dict:
    items = best_items_by_date(cell["bbox"], start, end, max_cloud)
    items = [i for i in items if i["coverage"] > 0.5]
    out = {"cell": cell["id"], "referenceDate": None, "scenes": [], "ponds": [], "itemsConsidered": len(items)}
    if not items:
        return out
    crs = f"EPSG:{items[0]['epsg'] or 32643}"
    bounds, shape, affine = fixed_grid(cell["bbox"], crs)

    # Reference: the requested date if this cell has it, else the clearest pass within 15 days
    ref_day = date.fromisoformat(reference_date)
    near = [i for i in items if abs((date.fromisoformat(i["date"]) - ref_day).days) <= REFERENCE_WINDOW_DAYS]
    if not near:
        return out
    ref_masks = {}
    for i in sorted(near, key=lambda i: (i["date"] != reference_date, i["cloud"])):
        water, invalid = read_masks(i, bounds, shape)
        ref_masks[i["date"]] = (water, invalid)
        if invalid.mean() < 0.05:
            break
    ref = min(ref_masks, key=lambda d: ref_masks[d][1].mean())
    water, invalid = ref_masks[ref]
    ponds = [p for p in detect_ponds(water, invalid, affine, crs, places_path=None) if in_core(cell["core"], p.lon, p.lat)]
    out["referenceDate"] = ref
    if not ponds:
        out["scenes"] = [{"date": i["date"], "id": i["id"], "coverage": i["coverage"]} for i in items]
        return out

    histories = {p.id: [] for p in ponds}
    for i in items:
        water_i, invalid_i = ref_masks.get(i["date"]) or read_masks(i, bounds, shape)
        for p in ponds:
            histories[p.id].append(measure_pond_pass(p, water_i, invalid_i, i["date"]).to_dict())
        out["scenes"].append({"date": i["date"], "id": i["id"], "coverage": i["coverage"]})
    out["ponds"] = [dict(p.to_dict(), id=f"{cell['id']}-{p.id}", history=histories[p.id]) for p in ponds]

    if region_id and (bucket or output_dir):
        try:
            for p in ponds:
                p.history = histories[p.id]

            from pipeline.imagery import export_cell_imagery

            export_cell_imagery(
                region_id=region_id,
                cell_id=cell["id"],
                items=items,
                ponds=ponds,
                affine=affine,
                crs=crs,
                bucket=bucket,
                s3_client=s3_client,
                output_dir=output_dir,
            )
        except Exception as e:
            logging.getLogger(__name__).warning("Failed cell imagery export for %s: %s", cell["id"], e)

    return out
