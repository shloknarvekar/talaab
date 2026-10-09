"""Imagery export module for Talaab Sentinel-2 pipeline.

Exports pond outlines (outlines.geojson) and true-colour satellite thumbnail crops
(256x256 JPEG) per pass along with an index (index.json) under web/public/imagery/{region}/.

Data credits: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search).
"""

from __future__ import annotations

import io
import json
import logging
import math
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

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
    pond_valid_dates: Dict[str, set] = {}

    for p in ponds:
        pid = p["id"] if isinstance(p, dict) else getattr(p, "id", None)
        history = p.get("history") if isinstance(p, dict) else getattr(p, "history", None)
        if pid and history is not None and isinstance(history, list):
            vd = {
                m["date"] for m in history
                if isinstance(m, dict) and m.get("valid") is True and "date" in m
            }
            pond_valid_dates[pid] = vd

        mask = p.get("footprint_mask") if isinstance(p, dict) else getattr(p, "footprint_mask", None)
        if mask is None or not np.any(mask):
            mask = p.get("water_component_mask") if isinstance(p, dict) else getattr(p, "water_component_mask", None)
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
                    vd = pond_valid_dates.get(pid)
                    if vd is not None and scene.date not in vd:
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


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    a = min(1.0, max(0.0, a))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def match_ponds_by_location(
    retained_ponds: List[dict],
    original_cell_ponds: List[dict],
    max_dist_km: float = 0.1,
    ambiguity_threshold_km: float = 0.02,
) -> Dict[str, dict]:
    """Match retained final district ponds (P001..) to original cell-level ponds (cXX-YY-P###..) by location.

    Guarantees:
    1. 1-to-1 unique mapping (no two retained ponds match the same original cell pond).
    2. Ambiguity rejection (rejects candidate if multiple candidates exist within max_dist_km
       and distance difference between top 2 candidates is less than ambiguity_threshold_km,
       unless top candidate is an exact match <= 1e-6 km). Evaluated in both directions.
    """
    kept_cands: Dict[str, List[Tuple[float, dict]]] = {}
    orig_cands: Dict[str, List[Tuple[float, dict]]] = {}

    for p_kept in retained_ponds:
        k_id = p_kept.get("id")
        k_lat, k_lon = p_kept.get("lat"), p_kept.get("lon")
        if not k_id or k_lat is None or k_lon is None:
            continue
        for p_orig in original_cell_ponds:
            o_id = p_orig.get("id")
            o_lat, o_lon = p_orig.get("lat"), p_orig.get("lon")
            if not o_id or o_lat is None or o_lon is None:
                continue
            dist = _haversine_km(float(k_lat), float(k_lon), float(o_lat), float(o_lon))
            if dist <= max_dist_km:
                kept_cands.setdefault(k_id, []).append((dist, p_orig))
                orig_cands.setdefault(o_id, []).append((dist, p_kept))

    ambiguous_kept = set()
    for k_id, cands in kept_cands.items():
        cands.sort(key=lambda x: x[0])
        if len(cands) >= 2:
            best_dist, second_dist = cands[0][0], cands[1][0]
            if best_dist > 1e-6 and (second_dist - best_dist) < ambiguity_threshold_km:
                logger.warning(
                    "Ambiguous location match for retained pond %s: candidates at %.4f km and %.4f km",
                    k_id, best_dist, second_dist,
                )
                ambiguous_kept.add(k_id)

    ambiguous_orig = set()
    for o_id, cands in orig_cands.items():
        cands.sort(key=lambda x: x[0])
        if len(cands) >= 2:
            best_dist, second_dist = cands[0][0], cands[1][0]
            if best_dist > 1e-6 and (second_dist - best_dist) < ambiguity_threshold_km:
                logger.warning(
                    "Ambiguous location match for original cell pond %s: candidates at %.4f km and %.4f km",
                    o_id, best_dist, second_dist,
                )
                ambiguous_orig.add(o_id)

    candidates = []
    for k_id, cands in kept_cands.items():
        if k_id in ambiguous_kept:
            continue
        best_dist, best_orig = cands[0]
        o_id = best_orig["id"]
        if o_id in ambiguous_orig:
            continue
        candidates.append((best_dist, k_id, best_orig))

    candidates.sort(key=lambda x: x[0])

    matches: Dict[str, dict] = {}
    used_kept_ids = set()
    used_orig_ids = set()

    for dist, k_id, p_orig in candidates:
        o_id = p_orig["id"]
        if k_id in used_kept_ids or o_id in used_orig_ids:
            continue
        matches[k_id] = p_orig
        used_kept_ids.add(k_id)
        used_orig_ids.add(o_id)

    return matches


def export_cell_imagery(
    region_id: str,
    cell_id: str,
    items: List[dict],
    ponds: List[dict | object],
    affine: Affine,
    crs: str,
    bucket: str | None = None,
    s3_client=None,
    output_dir: Path | None = None,
) -> dict:
    """Generate outlines.geojson, thumbnail JPEGs, and index.json for a district cell."""
    logger.info("Exporting cell imagery for region %s cell %s (%d ponds, %d items)", region_id, cell_id, len(ponds), len(items))

    cell_out_dir = None
    if output_dir is not None:
        cell_out_dir = output_dir / "imagery-cells" / cell_id
        cell_out_dir.mkdir(parents=True, exist_ok=True)

    features = []
    pond_masks = {}
    pond_ids = []
    pond_valid_dates = {}

    for p in ponds:
        if isinstance(p, dict):
            pid = p["id"]
            ref_area = p.get("refAreaHa") or p.get("ref_area_ha", 0.0)
            mask = p.get("water_component_mask")
            if mask is None or not np.any(mask):
                mask = p.get("footprint_mask")
            fp_mask = p.get("footprint_mask")
            history = p.get("history")
        else:
            pid = p.id
            ref_area = p.ref_area_ha
            mask = p.water_component_mask if (p.water_component_mask is not None and np.any(p.water_component_mask)) else p.footprint_mask
            fp_mask = p.footprint_mask
            history = getattr(p, "history", None)

        cell_pond_id = f"{cell_id}-{pid}" if not pid.startswith(cell_id) else pid
        pond_ids.append(cell_pond_id)

        if history is not None and isinstance(history, list):
            vd = {
                m["date"] for m in history
                if isinstance(m, dict) and m.get("valid") is True and "date" in m
            }
            pond_valid_dates[cell_pond_id] = vd

        if fp_mask is None or not np.any(fp_mask):
            fp_mask = mask
        pond_masks[cell_pond_id] = (mask, fp_mask)

        if mask is None or not np.any(mask):
            continue

        try:
            geom = extract_pond_outline_geometry(mask=mask, transform_affine=affine, crs=crs)
            feature = {
                "type": "Feature",
                "properties": {
                    "id": cell_pond_id,
                    "refAreaHa": round(float(ref_area), 2),
                },
                "geometry": geom,
            }
            features.append(feature)
        except Exception as e:
            logger.warning("Could not extract outline for cell pond %s: %s", cell_pond_id, e)

    outlines_doc = {
        "type": "FeatureCollection",
        "features": features,
    }
    outlines_bytes = json.dumps(outlines_doc, indent=2).encode("utf-8")

    if cell_out_dir:
        (cell_out_dir / "outlines.geojson").write_bytes(outlines_bytes)

    if bucket and s3_client:
        try:
            s3_client.put_object(
                Bucket=bucket,
                Key=f"data/{region_id}/imagery-cells/{cell_id}/outlines.geojson",
                Body=outlines_bytes,
                ContentType="application/json",
            )
        except Exception as e:
            logger.warning("Failed S3 upload of cell outlines for cell %s: %s", cell_id, e)

    pond_windows: Dict[str, Window] = {}
    pond_bboxes: Dict[str, List[float]] = {}
    pond_dates: Dict[str, List[str]] = {pid: [] for pid in pond_ids}

    visual_items = [i for i in items if i.get("visual")]
    if visual_items and pond_ids:
        try:
            with rasterio.open(visual_items[0]["visual"]) as v_src:
                first_fp = list(pond_masks.values())[0][1]
                h_cell, w_cell = first_fp.shape
                left = affine.c
                top = affine.f
                right = left + affine.a * w_cell
                bottom = top + affine.e * h_cell
                b_left, b_bottom, b_right, b_top = min(left, right), min(top, bottom), max(left, right), max(top, bottom)

                if str(v_src.crs) != str(crs):
                    b_left, b_bottom, b_right, b_top = transform_bounds(crs, v_src.crs, b_left, b_bottom, b_right, b_top)

                v_win = from_bounds(b_left, b_bottom, b_right, b_top, transform=v_src.transform).round_offsets()
                g_win_col_off = v_win.col_off
                g_win_row_off = v_win.row_off

                for pid in pond_ids:
                    _, fp_mask = pond_masks[pid]
                    if fp_mask is None or not np.any(fp_mask):
                        continue
                    win, bbox_wgs84 = get_pond_crop_window_and_bbox(
                        mask=fp_mask,
                        transform_affine=affine,
                        crs=crs,
                        g_win_col_off=g_win_col_off,
                        g_win_row_off=g_win_row_off,
                        padding_ratio=0.50,
                    )
                    pond_windows[pid] = win
                    pond_bboxes[pid] = bbox_wgs84
        except Exception as e:
            logger.warning("Failed to calculate COG crop windows for cell %s: %s", cell_id, e)

    for item in visual_items:
        date_str = item["date"]
        vis_url = item["visual"]
        try:
            with rasterio.open(vis_url) as v_src:
                for pid in pond_ids:
                    if pid not in pond_windows:
                        continue
                    vd = pond_valid_dates.get(pid)
                    if vd is not None and date_str not in vd:
                        continue

                    win = pond_windows[pid]
                    arr = v_src.read(window=win, boundless=True, fill_value=0)
                    if arr.shape[0] < 3 or arr.shape[1] == 0 or arr.shape[2] == 0:
                        continue
                    rgb = np.transpose(arr[:3, :, :], (1, 2, 0))
                    img = Image.fromarray(rgb, mode="RGB")
                    resized = img.resize((256, 256), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    resized.save(buf, format="JPEG", quality=80)
                    jpg_bytes = buf.getvalue()

                    written_local = False
                    written_s3 = False

                    if cell_out_dir:
                        try:
                            p_dir = cell_out_dir / pid
                            p_dir.mkdir(parents=True, exist_ok=True)
                            (p_dir / f"{date_str}.jpg").write_bytes(jpg_bytes)
                            written_local = True
                        except Exception as e:
                            logger.warning("Failed local save of cell thumbnail %s %s: %s", pid, date_str, e)

                    if bucket and s3_client:
                        try:
                            s3_client.put_object(
                                Bucket=bucket,
                                Key=f"data/{region_id}/imagery-cells/{cell_id}/{pid}/{date_str}.jpg",
                                Body=jpg_bytes,
                                ContentType="image/jpeg",
                            )
                            written_s3 = True
                        except Exception as e:
                            logger.warning("Failed S3 upload of cell thumbnail %s %s: %s", pid, date_str, e)

                    if written_local or written_s3:
                        pond_dates[pid].append(date_str)
        except Exception as e:
            logger.warning("Failed to generate cell thumbnails for date %s in cell %s: %s", date_str, cell_id, e)

    credit_year = "2024" if "2024" in region_id else "2026"
    index_doc = {
        "region": region_id,
        "cell": cell_id,
        "credit": f"Contains modified Copernicus Sentinel data {credit_year}, via AWS Open Data",
        "ponds": {
            pid: {
                "dates": pond_dates[pid],
                "bbox": pond_bboxes.get(pid, [0.0, 0.0, 0.0, 0.0]),
            }
            for pid in pond_ids
        },
    }
    index_bytes = json.dumps(index_doc, indent=2).encode("utf-8")

    if cell_out_dir:
        (cell_out_dir / "index.json").write_bytes(index_bytes)

    if bucket and s3_client:
        try:
            s3_client.put_object(
                Bucket=bucket,
                Key=f"data/{region_id}/imagery-cells/{cell_id}/index.json",
                Body=index_bytes,
                ContentType="application/json",
            )
        except Exception as e:
            logger.warning("Failed S3 upload of cell index for cell %s: %s", cell_id, e)

    return index_doc


def promote_district_imagery(
    region_id: str,
    kept_ponds: List[dict],
    original_cell_ponds: List[dict],
    bucket: str | None = None,
    s3_client=None,
    output_dir: Path | None = None,
) -> dict:
    """Promote cell-level imagery to final district imagery for retained ponds (P001..)."""
    logger.info("Promoting imagery for district region %s (%d kept ponds)", region_id, len(kept_ponds))

    matches = match_ponds_by_location(kept_ponds, original_cell_ponds)

    cell_map: Dict[str, Dict[str, str]] = {}
    for final_id, orig_p in matches.items():
        cell_pond_id = orig_p["id"]
        cell_id = cell_pond_id.rsplit("-P", 1)[0]
        cell_map.setdefault(cell_id, {})[cell_pond_id] = final_id

    district_features = []
    district_index_ponds = {}

    for cell_id, pond_id_map in cell_map.items():
        outlines_doc = None
        index_doc = None

        if bucket and s3_client:
            try:
                o_obj = s3_client.get_object(Bucket=bucket, Key=f"data/{region_id}/imagery-cells/{cell_id}/outlines.geojson")
                outlines_doc = json.loads(o_obj["Body"].read().decode("utf-8"))
            except Exception:
                pass
            try:
                i_obj = s3_client.get_object(Bucket=bucket, Key=f"data/{region_id}/imagery-cells/{cell_id}/index.json")
                index_doc = json.loads(i_obj["Body"].read().decode("utf-8"))
            except Exception:
                pass

        if not outlines_doc or not index_doc:
            if output_dir:
                cell_dir = output_dir / "imagery-cells" / cell_id
                o_file = cell_dir / "outlines.geojson"
                i_file = cell_dir / "index.json"
                if o_file.exists():
                    outlines_doc = json.loads(o_file.read_text(encoding="utf-8"))
                if i_file.exists():
                    index_doc = json.loads(i_file.read_text(encoding="utf-8"))

        if not outlines_doc or not index_doc:
            logger.warning("Missing cell imagery docs for cell %s", cell_id)
            continue

        cell_features_by_id = {f["properties"]["id"]: f for f in outlines_doc.get("features", [])}
        cell_index_ponds = index_doc.get("ponds", {})

        for cell_pond_id, final_id in pond_id_map.items():
            kp = next((p for p in kept_ponds if p["id"] == final_id), None)
            kp_valid_dates = None
            if kp and isinstance(kp.get("history"), list):
                kp_valid_dates = {
                    m["date"] for m in kp["history"]
                    if isinstance(m, dict) and m.get("valid") is True and "date" in m
                }

            if cell_pond_id in cell_features_by_id:
                feat = json.loads(json.dumps(cell_features_by_id[cell_pond_id]))
                feat["properties"]["id"] = final_id
                if kp and "refAreaHa" in kp:
                    feat["properties"]["refAreaHa"] = round(float(kp["refAreaHa"]), 2)
                district_features.append(feat)

            if cell_pond_id in cell_index_ponds:
                p_info = cell_index_ponds[cell_pond_id]
                promoted_dates = []
                for d in p_info.get("dates", []):
                    if kp_valid_dates is not None and d not in kp_valid_dates:
                        continue

                    copied_local = False
                    copied_s3 = False

                    if bucket and s3_client:
                        src_key = f"data/{region_id}/imagery-cells/{cell_id}/{cell_pond_id}/{d}.jpg"
                        dst_key = f"data/{region_id}/imagery/{final_id}/{d}.jpg"
                        try:
                            s3_client.copy_object(
                                Bucket=bucket,
                                CopySource={"Bucket": bucket, "Key": src_key},
                                Key=dst_key,
                            )
                            copied_s3 = True
                        except Exception as e:
                            logger.warning("Failed to copy S3 thumbnail %s -> %s: %s", src_key, dst_key, e)

                    if output_dir:
                        src_file = output_dir / "imagery-cells" / cell_id / cell_pond_id / f"{d}.jpg"
                        dst_file = output_dir / "imagery" / final_id / f"{d}.jpg"
                        if src_file.exists():
                            try:
                                dst_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(src_file, dst_file)
                                copied_local = True
                            except Exception as e:
                                logger.warning("Failed local copy of thumbnail %s -> %s: %s", src_file, dst_file, e)

                    if copied_local or copied_s3:
                        promoted_dates.append(d)

                district_index_ponds[final_id] = {
                    "dates": promoted_dates,
                    "bbox": p_info.get("bbox", [0.0, 0.0, 0.0, 0.0]),
                }

    district_outlines = {
        "type": "FeatureCollection",
        "features": district_features,
    }
    district_outlines_bytes = json.dumps(district_outlines, indent=2).encode("utf-8")

    if output_dir:
        dist_imagery_dir = output_dir / "imagery"
        dist_imagery_dir.mkdir(parents=True, exist_ok=True)
        (dist_imagery_dir / "outlines.geojson").write_bytes(district_outlines_bytes)

    if bucket and s3_client:
        try:
            s3_client.put_object(
                Bucket=bucket,
                Key=f"data/{region_id}/imagery/outlines.geojson",
                Body=district_outlines_bytes,
                ContentType="application/json",
            )
        except Exception as e:
            logger.warning("Failed S3 upload of district outlines for %s: %s", region_id, e)

    credit_year = "2024" if "2024" in region_id else "2026"
    district_index = {
        "region": region_id,
        "credit": f"Contains modified Copernicus Sentinel data {credit_year}, via AWS Open Data",
        "ponds": district_index_ponds,
    }
    district_index_bytes = json.dumps(district_index, indent=2).encode("utf-8")

    if output_dir:
        (output_dir / "imagery" / "index.json").write_bytes(district_index_bytes)

    if bucket and s3_client:
        try:
            s3_client.put_object(
                Bucket=bucket,
                Key=f"data/{region_id}/imagery/index.json",
                Body=district_index_bytes,
                ContentType="application/json",
            )
        except Exception as e:
            logger.warning("Failed S3 upload of district index for %s: %s", region_id, e)

    return district_index
