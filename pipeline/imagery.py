"""Imagery export module for Talaab Sentinel-2 pipeline.

Exports pond outlines (outlines.geojson) and true-colour satellite thumbnail crops
(256x256 JPEG) per pass along with an index (index.json) under web/public/imagery/{region}/.

Data credits: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Tuple

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.transform import Affine
from rasterio.warp import transform, transform_bounds
from rasterio.windows import Window, from_bounds
from PIL import Image

from pipeline.stac import STACScene

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGERY_DIR = REPO_ROOT / "web" / "public" / "imagery"


def rdp_simplify(points: list[list[float]], epsilon: float = 0.00008) -> list[list[float]]:
    """Simplify 2D point sequence using Ramer-Douglas-Peucker algorithm."""
    if len(points) <= 2:
        return points

    pts = np.array(points)
    p1, p2 = pts[0], pts[-1]
    line_vec = p2 - p1
    line_len = np.linalg.norm(line_vec)

    if line_len == 0:
        dists = np.linalg.norm(pts - p1, axis=1)
    else:
        line_unit = line_vec / line_len
        vec_p1 = pts - p1
        proj = np.outer(np.dot(vec_p1, line_unit), line_unit)
        dists = np.linalg.norm(vec_p1 - proj, axis=1)

    idx = int(np.argmax(dists))
    if dists[idx] > epsilon:
        r1 = rdp_simplify(points[: idx + 1], epsilon)
        r2 = rdp_simplify(points[idx:], epsilon)
        return r1[:-1] + r2

    return [points[0], points[-1]]


def simplify_ring(ring: list[list[float]], epsilon: float = 0.00008) -> list[list[float]]:
    """Simplify a closed polygon coordinate ring while preserving topology."""
    if len(ring) < 4:
        return ring

    res = rdp_simplify(ring, epsilon)
    # If over-simplified below valid polygon ring size, retry with finer epsilon
    if len(res) < 4:
        res = rdp_simplify(ring, epsilon / 8.0)
    if len(res) < 4:
        res = ring

    # Ensure closed coordinate ring
    if res[0] != res[-1]:
        res.append(res[0])

    return res


def extract_pond_outline_geometry(
    mask: np.ndarray,
    transform_affine: Affine,
    crs,
    epsilon: float = 0.00008,
) -> dict:
    """Extract GeoJSON Polygon/MultiPolygon geometry from binary mask in EPSG:4326."""
    if not np.any(mask):
        raise ValueError("Cannot extract outline from empty mask")

    extracted_shapes = list(shapes(mask.astype(np.uint8), mask=mask, transform=transform_affine))
    if not extracted_shapes:
        raise ValueError("No shapes extracted from mask")

    polygons_coords = []
    for geom, val in extracted_shapes:
        if val != 1:
            continue
        rings = []
        for raw_ring in geom["coordinates"]:
            xs = [pt[0] for pt in raw_ring]
            ys = [pt[1] for pt in raw_ring]
            lons, lats = transform(crs, "EPSG:4326", xs, ys)
            ring_wgs = [[round(float(lon), 6), round(float(lat), 6)] for lon, lat in zip(lons, lats)]
            simplified = simplify_ring(ring_wgs, epsilon=epsilon)
            rings.append(simplified)
        if rings:
            polygons_coords.append(rings)

    if not polygons_coords:
        raise ValueError("Failed to construct polygon rings")

    if len(polygons_coords) == 1:
        return {"type": "Polygon", "coordinates": polygons_coords[0]}
    else:
        return {"type": "MultiPolygon", "coordinates": polygons_coords}


def get_pond_crop_window_and_bbox(
    mask: np.ndarray,
    transform_affine: Affine,
    crs,
    g_win_col_off: float,
    g_win_row_off: float,
    padding_ratio: float = 0.50,
) -> Tuple[Window, List[float]]:
    """Compute COG pixel Window and WGS84 bounding box [min_lon, min_lat, max_lon, max_lat]."""
    y_indices, x_indices = np.where(mask)
    if len(y_indices) == 0:
        raise ValueError("Empty mask passed to get_pond_crop_window_and_bbox")

    y_min, y_max = int(np.min(y_indices)), int(np.max(y_indices))
    x_min, x_max = int(np.min(x_indices)), int(np.max(x_indices))

    height = y_max - y_min + 1
    width = x_max - x_min + 1
    side = max(height, width)
    target_size = int(round(side * (1.0 + 2.0 * padding_ratio)))
    target_size = max(target_size, 20)  # Minimum 20 pixels

    y_center = (y_min + y_max) / 2.0
    x_center = (x_min + x_max) / 2.0

    crop_ymin = int(round(y_center - target_size / 2.0))
    crop_ymax = crop_ymin + target_size
    crop_xmin = int(round(x_center - target_size / 2.0))
    crop_xmax = crop_xmin + target_size

    # Bound within region array dimensions
    h_max, w_max = mask.shape
    if crop_ymin < 0:
        crop_ymax = min(h_max, crop_ymax - crop_ymin)
        crop_ymin = 0
    if crop_ymax > h_max:
        crop_ymin = max(0, crop_ymin - (crop_ymax - h_max))
        crop_ymax = h_max

    if crop_xmin < 0:
        crop_xmax = min(w_max, crop_xmax - crop_xmin)
        crop_xmin = 0
    if crop_xmax > w_max:
        crop_xmin = max(0, crop_xmin - (crop_xmax - w_max))
        crop_xmax = w_max

    # COG window
    window_in_cog = Window(
        col_off=int(round(g_win_col_off)) + crop_xmin,
        row_off=int(round(g_win_row_off)) + crop_ymin,
        width=max(1, crop_xmax - crop_xmin),
        height=max(1, crop_ymax - crop_ymin),
    )

    # WGS84 bounding box calculation
    x_min_utm, y_max_utm = transform_affine @ (crop_xmin, crop_ymin)
    x_max_utm, y_min_utm = transform_affine @ (crop_xmax, crop_ymax)
    lons, lats = transform(crs, "EPSG:4326", [x_min_utm, x_max_utm], [y_min_utm, y_max_utm])
    bbox_wgs84 = [
        round(float(min(lons)), 4),
        round(float(min(lats)), 4),
        round(float(max(lons)), 4),
        round(float(max(lats)), 4),
    ]

    return window_in_cog, bbox_wgs84


def export_region_imagery(
    region_id: str,
    scenes: List[STACScene],
    ponds: List[dict],
    ref_bands: dict,
    bbox: List[float],
    output_dir: Path | None = None,
) -> Path:
    """Generate outlines.geojson, thumbnail JPEGs, and index.json for a region."""
    if output_dir is None:
        output_dir = DEFAULT_IMAGERY_DIR / region_id

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Exporting imagery for region %s to %s", region_id, output_dir)

    # 1. Generate outlines.geojson
    features = []
    for p in ponds:
        mask = p.get("water_component_mask")
        if mask is None or not np.any(mask):
            mask = p.get("footprint_mask")

        if mask is None or not np.any(mask):
            logger.warning("Skipping outline for pond %s: no geometry mask available", p["id"])
            continue

        geom = extract_pond_outline_geometry(
            mask=mask,
            transform_affine=ref_bands["transform"],
            crs=ref_bands["crs"],
        )
        feature = {
            "type": "Feature",
            "properties": {
                "id": p["id"],
                "refAreaHa": round(float(p["refAreaHa"]), 2),
            },
            "geometry": geom,
        }
        features.append(feature)

    outlines_doc = {
        "type": "FeatureCollection",
        "features": features,
    }

    outlines_file = output_dir / "outlines.geojson"
    outlines_file.write_text(json.dumps(outlines_doc, indent=2), encoding="utf-8")
    logger.info("Wrote %s (%d features)", outlines_file, len(features))

    # 2. Determine region COG window offsets
    first_green_url = scenes[0].green_url
    with rasterio.open(first_green_url) as g_src:
        left, bottom, right, top = transform_bounds("EPSG:4326", g_src.crs, *bbox)
        g_win = from_bounds(left, bottom, right, top, transform=g_src.transform).round_offsets()
        g_win_col_off = g_win.col_off
        g_win_row_off = g_win.row_off

    # 3. Compute thumbnail crop windows & bounding boxes per pond
    pond_windows: Dict[str, Window] = {}
    pond_bboxes: Dict[str, List[float]] = {}
    pond_dates: Dict[str, List[str]] = {p["id"]: [] for p in ponds}

    for p in ponds:
        mask = p.get("footprint_mask")
        if mask is None or not np.any(mask):
            mask = p.get("water_component_mask")
        if mask is None or not np.any(mask):
            continue

        win, bbox_wgs84 = get_pond_crop_window_and_bbox(
            mask=mask,
            transform_affine=ref_bands["transform"],
            crs=ref_bands["crs"],
            g_win_col_off=g_win_col_off,
            g_win_row_off=g_win_row_off,
            padding_ratio=0.50,
        )
        pond_windows[p["id"]] = win
        pond_bboxes[p["id"]] = bbox_wgs84
        (output_dir / p["id"]).mkdir(parents=True, exist_ok=True)

    # 4. Generate thumbnail JPEGs scene by scene
    for idx, scene in enumerate(scenes, start=1):
        try:
            with rasterio.open(scene.visual_url) as v_src:
                for p in ponds:
                    pid = p["id"]
                    if pid not in pond_windows:
                        continue
                    win = pond_windows[pid]
                    arr = v_src.read(window=win)
                    if arr.shape[0] < 3 or arr.shape[1] == 0 or arr.shape[2] == 0:
                        continue
                    rgb = np.transpose(arr[:3, :, :], (1, 2, 0))
                    img = Image.fromarray(rgb, mode="RGB")
                    resized = img.resize((256, 256), Image.Resampling.LANCZOS)
                    jpg_path = output_dir / pid / f"{scene.date}.jpg"
                    resized.save(jpg_path, format="JPEG", quality=80)
                    pond_dates[pid].append(scene.date)
        except Exception as e:
            logger.warning("Failed to generate thumbnails for scene %s (%s): %s", scene.date, scene.id, e)

    # 5. Build and export index.json
    credit_year = "2024" if "2024" in region_id else "2026"
    index_doc = {
        "region": region_id,
        "credit": f"Contains modified Copernicus Sentinel data {credit_year}, via AWS Open Data",
        "ponds": {
            pid: {
                "dates": pond_dates[pid],
                "bbox": pond_bboxes.get(pid, [0.0, 0.0, 0.0, 0.0]),
            }
            for pid in pond_dates
        },
    }

    index_file = output_dir / "index.json"
    index_file.write_text(json.dumps(index_doc, indent=2), encoding="utf-8")
    logger.info("Wrote %s", index_file)

    return output_dir
