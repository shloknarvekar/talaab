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
    extract_pond_outline_geometry,
    export_region_imagery,
    get_pond_crop_window_and_bbox,
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
