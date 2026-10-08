"""Tests for pipeline/ponds.py pond detection and measurement module."""

import numpy as np
from rasterio.transform import Affine

from pipeline.ponds import (
    DetectedPond,
    PondMeasurement,
    _haversine_km,
    detect_ponds,
    find_nearest_place,
    measure_pond_pass,
)


def test_haversine_km():
    # Distance between Latur center and nearby point (~11 km)
    dist = _haversine_km(18.4088, 76.5604, 18.5000, 76.5604)
    assert 9.0 < dist < 11.0


def test_find_nearest_place():
    places = [
        {"name": "Bhadgaon", "nameMr": "भडगाव", "lat": 18.40, "lon": 76.55},
        {"name": "Murud", "nameMr": "मुरुड", "lat": 18.25, "lon": 76.35},
    ]

    # Close point (within 5 km)
    place_str, place_mr = find_nearest_place(18.41, 76.55, places, max_dist_km=5.0)
    assert place_str == "near Bhadgaon"
    assert place_mr == "भडगाव"

    # Far point (> 5 km)
    far_str, far_mr = find_nearest_place(19.00, 77.00, places, max_dist_km=5.0)
    assert far_str == ""
    assert far_mr is None


def test_detect_ponds():
    # 100x100 grid at 10m res -> pixel area = 0.01 ha
    # Create a 20x10 water patch (200 pixels = 2.0 ha)
    water_mask = np.zeros((100, 100), dtype=bool)
    water_mask[10:30, 10:20] = True
    scl_invalid = np.zeros((100, 100), dtype=bool)

    transform_affine = Affine(10.0, 0.0, 700000.0, 0.0, -10.0, 2030000.0)
    crs = "EPSG:32643"

    ponds = detect_ponds(
        water_mask=water_mask,
        scl_invalid_mask=scl_invalid,
        transform_affine=transform_affine,
        crs=crs,
        min_ha=1.0,
        max_ha=200.0,
        pixel_area_ha=0.01,
        places_path=None,
    )

    assert len(ponds) == 1
    assert ponds[0].id == "P001"
    assert np.isclose(ponds[0].ref_area_ha, 2.0)
    # Footprint dilated by 2px (default 4-connectivity) should be 324 pixels
    assert np.sum(ponds[0].footprint_mask) == 324


def test_measure_pond_pass():
    footprint = np.zeros((50, 50), dtype=bool)
    footprint[10:20, 10:20] = True  # 100 px footprint

    pond = DetectedPond(
        id="P001",
        lat=18.4,
        lon=76.5,
        place="near Village",
        place_mr=None,
        ref_area_ha=1.0,
        footprint_mask=footprint,
    )

    water_mask = np.zeros((50, 50), dtype=bool)
    water_mask[10:15, 10:20] = True  # 50 px water = 0.5 ha
    scl_invalid = np.zeros((50, 50), dtype=bool)

    # Valid pass (< 20% invalid SCL)
    meas_valid = measure_pond_pass(pond, water_mask, scl_invalid, "2024-01-16", pixel_area_ha=0.01)
    assert meas_valid.valid is True
    assert np.isclose(meas_valid.area_ha, 0.5)

    # Invalid pass (> 20% invalid SCL in footprint)
    scl_invalid[10:15, 10:20] = True  # 50 px invalid out of 100 footprint px = 50%
    meas_invalid = measure_pond_pass(pond, water_mask, scl_invalid, "2024-01-16", pixel_area_ha=0.01)
    assert meas_invalid.valid is False
