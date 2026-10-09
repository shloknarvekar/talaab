"""Unit tests for pipeline.imagery module."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from rasterio.transform import from_origin
from rasterio.windows import Window
from PIL import Image

from pipeline.imagery import (
    export_cell_imagery,
    export_region_imagery,
    extract_pond_outline_geometry,
    get_pond_crop_window_and_bbox,
    match_ponds_by_location,
    promote_district_imagery,
    rdp_simplify,
    simplify_ring,
)
from pipeline.stac import STACScene


def test_rdp_simplify():
    # Straight line with intermediate redundant points
    line = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]
    simplified = rdp_simplify(line, epsilon=0.01)
    assert len(simplified) == 2
    assert simplified == [[0.0, 0.0], [3.0, 0.0]]

    # Spike point should be retained
    spike = [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]
    simplified_spike = rdp_simplify(spike, epsilon=0.01)
    assert len(simplified_spike) == 3


def test_simplify_ring():
    square_ring = [
        [76.500, 18.300],
        [76.505, 18.300],
        [76.510, 18.300],
        [76.510, 18.310],
        [76.500, 18.310],
        [76.500, 18.300],
    ]
    res = simplify_ring(square_ring, epsilon=0.0001)
    assert res[0] == res[-1]  # Closed ring
    assert len(res) >= 4  # Valid GeoJSON ring


def test_extract_pond_outline_geometry():
    # Create 50x50 boolean water mask with a 20x20 square in center
    mask = np.zeros((50, 50), dtype=bool)
    mask[15:35, 15:35] = True

    # Simple UTM affine transform (10m pixels)
    transform_affine = from_origin(500000.0, 2000000.0, 10.0, 10.0)
    crs = "EPSG:32643"

    geom = extract_pond_outline_geometry(mask, transform_affine, crs)
    assert geom["type"] in ("Polygon", "MultiPolygon")
    assert "coordinates" in geom
    coords = geom["coordinates"]
    assert len(coords) > 0


def test_extract_pond_outline_empty_mask():
    mask = np.zeros((50, 50), dtype=bool)
    transform_affine = from_origin(500000.0, 2000000.0, 10.0, 10.0)
    with pytest.raises(ValueError, match="empty mask"):
        extract_pond_outline_geometry(mask, transform_affine, "EPSG:32643")


def test_get_pond_crop_window_and_bbox():
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 40:60] = True

    transform_affine = from_origin(500000.0, 2000000.0, 10.0, 10.0)
    crs = "EPSG:32643"

    win, bbox = get_pond_crop_window_and_bbox(
        mask=mask,
        transform_affine=transform_affine,
        crs=crs,
        g_win_col_off=1000.0,
        g_win_row_off=2000.0,
        padding_ratio=0.50,
    )

    assert isinstance(win, Window)
    assert win.width > 0 and win.height > 0
    assert len(bbox) == 4
    # Check [min_lon, min_lat, max_lon, max_lat] order
    assert bbox[0] <= bbox[2]
    assert bbox[1] <= bbox[3]


def test_export_region_imagery(tmp_path: Path):
    region_id = "latur-2024"
    scenes = [
        STACScene(
            id="S2B_20240116",
            date="2024-01-16",
            datetime_utc=datetime(2024, 1, 16, 5, 30),
            cloud_cover=2.5,
            green_url="https://example.com/green.tif",
            nir_url="https://example.com/nir.tif",
            scl_url="https://example.com/scl.tif",
            visual_url="https://example.com/visual.tif",
        )
    ]

    mask = np.zeros((50, 50), dtype=bool)
    mask[15:35, 15:35] = True

    ponds = [
        {
            "id": "P001",
            "refAreaHa": 4.0,
            "footprint_mask": mask,
            "water_component_mask": mask,
        }
    ]

    transform_affine = from_origin(500000.0, 2000000.0, 10.0, 10.0)
    ref_bands = {
        "transform": transform_affine,
        "crs": "EPSG:32643",
    }
    bbox = [76.47, 18.33, 76.62, 18.48]

    # Mock rasterio.open for green and visual assets
    mock_src = MagicMock()
    mock_src.__enter__.return_value = mock_src
    mock_src.crs = "EPSG:32643"
    mock_src.transform = transform_affine

    # 3-band uint8 RGB array (3, 40, 40)
    rgb_arr = np.full((3, 40, 40), 128, dtype=np.uint8)
    mock_src.read.return_value = rgb_arr

    with patch("rasterio.open", return_value=mock_src):
        out_dir = export_region_imagery(
            region_id=region_id,
            scenes=scenes,
            ponds=ponds,
            ref_bands=ref_bands,
            bbox=bbox,
            output_dir=tmp_path / "imagery" / region_id,
        )

    # Check created files according to docs/imagery-contract.md
    assert (out_dir / "outlines.geojson").exists()
    assert (out_dir / "index.json").exists()
    assert (out_dir / "P001" / "2024-01-16.jpg").exists()

    # Verify index.json content
    index_data = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
    assert index_data["region"] == "latur-2024"
    assert "Copernicus" in index_data["credit"]
    assert "P001" in index_data["ponds"]
    assert index_data["ponds"]["P001"]["dates"] == ["2024-01-16"]
    assert len(index_data["ponds"]["P001"]["bbox"]) == 4

    # Verify outlines.geojson content
    outlines_data = json.loads((out_dir / "outlines.geojson").read_text(encoding="utf-8"))
    assert outlines_data["type"] == "FeatureCollection"
    assert len(outlines_data["features"]) == 1
    assert outlines_data["features"][0]["properties"]["id"] == "P001"
    assert outlines_data["features"][0]["properties"]["refAreaHa"] == 4.0

    # Verify thumbnail image dimensions
    img = Image.open(out_dir / "P001" / "2024-01-16.jpg")
    assert img.size == (256, 256)
    assert img.format == "JPEG"


def test_match_ponds_by_location():
    kept = [{"id": "P001", "lat": 18.35, "lon": 76.50, "refAreaHa": 10.0}]
    orig = [
        {"id": "c03-02-P001", "lat": 18.3501, "lon": 76.5001, "refAreaHa": 10.0},
        {"id": "c03-02-P002", "lat": 18.45, "lon": 76.60, "refAreaHa": 5.0},
    ]
    matched = match_ponds_by_location(kept, orig)
    assert "P001" in matched
    assert matched["P001"]["id"] == "c03-02-P001"


def test_match_ponds_by_location_ambiguity():
    # 2 orig cell ponds within ambiguity_threshold_km (0.02 km = 20 m) of 1 kept pond
    # Distances to (18.35, 76.50):
    # orig1: (18.3501, 76.5001) ~ 0.015 km
    # orig2: (18.3502, 76.5002) ~ 0.030 km
    # diff = 0.015 km < 0.02 km -> ambiguous!
    kept = [{"id": "P001", "lat": 18.35, "lon": 76.50}]
    orig = [
        {"id": "c01-P001", "lat": 18.3501, "lon": 76.5001},
        {"id": "c01-P002", "lat": 18.3502, "lon": 76.5002},
    ]
    matched = match_ponds_by_location(kept, orig)
    assert "P001" not in matched

    # 2 kept ponds competing for 1 orig pond within 20m
    kept_dual = [
        {"id": "P001", "lat": 18.3501, "lon": 76.5001},
        {"id": "P002", "lat": 18.3502, "lon": 76.5002},
    ]
    orig_single = [{"id": "c01-P001", "lat": 18.35, "lon": 76.50}]
    matched_dual = match_ponds_by_location(kept_dual, orig_single)
    assert len(matched_dual) == 0


def test_export_cell_imagery_valid_dates_only(tmp_path: Path):
    cell_id = "c03-02"
    region_id = "latur-district-2024"
    mask = np.zeros((50, 50), dtype=bool)
    mask[15:35, 15:35] = True
    affine = from_origin(500000.0, 2000000.0, 10.0, 10.0)

    items = [
        {"date": "2024-01-16", "id": "S2B_20240116", "visual": "https://example.com/v1.tif"},
        {"date": "2024-01-21", "id": "S2B_20240121", "visual": "https://example.com/v2.tif"},
    ]

    pond_dict = {
        "id": "c03-02-P001",
        "refAreaHa": 4.0,
        "lat": 18.08,
        "lon": 50.00,
        "footprint_mask": mask,
        "water_component_mask": mask,
        "history": [
            {"date": "2024-01-16", "valid": True},
            {"date": "2024-01-21", "valid": False},
        ],
    }

    mock_src = MagicMock()
    mock_src.__enter__.return_value = mock_src
    mock_src.crs = "EPSG:32643"
    mock_src.transform = affine
    rgb_arr = np.full((3, 50, 50), 128, dtype=np.uint8)
    mock_src.read.return_value = rgb_arr

    with patch("rasterio.open", return_value=mock_src):
        export_cell_imagery(
            region_id=region_id,
            cell_id=cell_id,
            items=items,
            ponds=[pond_dict],
            affine=affine,
            crs="EPSG:32643",
            output_dir=tmp_path,
        )

    cell_out_dir = tmp_path / "imagery-cells" / cell_id
    assert (cell_out_dir / "c03-02-P001" / "2024-01-16.jpg").exists()
    assert not (cell_out_dir / "c03-02-P001" / "2024-01-21.jpg").exists()

    index_data = json.loads((cell_out_dir / "index.json").read_text(encoding="utf-8"))
    assert index_data["ponds"]["c03-02-P001"]["dates"] == ["2024-01-16"]


def test_export_cell_imagery_and_promote(tmp_path: Path):
    region_id = "latur-district-2024"
    cell_id = "c03-02"

    mask = np.zeros((50, 50), dtype=bool)
    mask[15:35, 15:35] = True
    affine = from_origin(500000.0, 2000000.0, 10.0, 10.0)

    items = [{
        "date": "2024-01-16",
        "id": "S2B_20240116",
        "visual": "https://example.com/visual.tif",
    }]

    ponds = [{
        "id": "c03-02-P001",
        "refAreaHa": 4.0,
        "lat": 18.08,
        "lon": 50.00,
        "footprint_mask": mask,
        "water_component_mask": mask,
    }]

    mock_src = MagicMock()
    mock_src.__enter__.return_value = mock_src
    mock_src.crs = "EPSG:32643"
    mock_src.transform = affine
    rgb_arr = np.full((3, 50, 50), 128, dtype=np.uint8)
    mock_src.read.return_value = rgb_arr

    with patch("rasterio.open", return_value=mock_src):
        export_cell_imagery(
            region_id=region_id,
            cell_id=cell_id,
            items=items,
            ponds=ponds,
            affine=affine,
            crs="EPSG:32643",
            output_dir=tmp_path,
        )

    cell_out_dir = tmp_path / "imagery-cells" / cell_id
    assert (cell_out_dir / "outlines.geojson").exists()
    assert (cell_out_dir / "index.json").exists()
    assert (cell_out_dir / "c03-02-P001" / "2024-01-16.jpg").exists()

    kept_ponds = [{
        "id": "P001",
        "lat": 18.08,
        "lon": 50.00,
        "refAreaHa": 4.0,
    }]

    promote_district_imagery(
        region_id=region_id,
        kept_ponds=kept_ponds,
        original_cell_ponds=ponds,
        output_dir=tmp_path,
    )

    dist_out_dir = tmp_path / "imagery"
    assert (dist_out_dir / "outlines.geojson").exists()
    assert (dist_out_dir / "index.json").exists()
    assert (dist_out_dir / "P001" / "2024-01-16.jpg").exists()

    index_data = json.loads((dist_out_dir / "index.json").read_text(encoding="utf-8"))
    assert "P001" in index_data["ponds"]
    assert index_data["ponds"]["P001"]["dates"] == ["2024-01-16"]


def test_match_ponds_by_location_missing_coords():
    kept = [
        {"id": "P001", "lat": 18.35, "lon": 76.50},
        {"id": "P002", "lat": None, "lon": 76.50},
    ]
    orig = [
        {"id": "c01-P001", "lat": 18.35001, "lon": 76.50001},
        {"id": "c01-P002", "lat": 18.40},
    ]
    matched = match_ponds_by_location(kept, orig)
    assert "P001" in matched
    assert matched["P001"]["id"] == "c01-P001"
    assert "P002" not in matched


def test_match_ponds_by_location_empty_input():
    assert match_ponds_by_location([], []) == {}
    assert match_ponds_by_location([{"id": "P001", "lat": 18.35, "lon": 76.50}], []) == {}


def test_export_cell_imagery_no_visual(tmp_path: Path):
    region_id = "latur-district-2024"
    cell_id = "c03-02"
    mask = np.zeros((50, 50), dtype=bool)
    mask[15:35, 15:35] = True
    affine = from_origin(500000.0, 2000000.0, 10.0, 10.0)

    items = [{"date": "2024-01-16", "id": "S2B_20240116"}]
    ponds = [{
        "id": "c03-02-P001",
        "refAreaHa": 4.0,
        "lat": 18.08,
        "lon": 50.00,
        "footprint_mask": mask,
        "water_component_mask": mask,
    }]

    export_cell_imagery(
        region_id=region_id,
        cell_id=cell_id,
        items=items,
        ponds=ponds,
        affine=affine,
        crs="EPSG:32643",
        output_dir=tmp_path,
    )

    cell_out_dir = tmp_path / "imagery-cells" / cell_id
    assert (cell_out_dir / "outlines.geojson").exists()
    assert (cell_out_dir / "index.json").exists()