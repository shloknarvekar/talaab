"""Tests for pipeline/water.py water extraction and SCL masking module."""

import numpy as np
from pipeline.water import DEFAULT_INVALID_SCL, compute_ndwi, get_scl_invalid_mask


def test_compute_ndwi():
    # Green higher than NIR -> Positive NDWI (Water)
    green = np.array([[2000, 500]], dtype=np.uint16)
    nir = np.array([[500, 2000]], dtype=np.uint16)

    ndwi = compute_ndwi(green, nir)

    # (2000-500)/(2000+500) = 1500/2500 = 0.60
    assert np.isclose(ndwi[0, 0], 0.60)
    # (500-2000)/(500+2000) = -1500/2500 = -0.60
    assert np.isclose(ndwi[0, 1], -0.60)


def test_get_scl_invalid_mask():
    # SCL values: 0=no_data, 4=vegetation(valid), 6=water(valid), 8=cloud_med(invalid), 9=cloud_high(invalid)
    scl = np.array([[0, 4], [6, 8], [9, 10]], dtype=np.uint8)
    invalid_mask = get_scl_invalid_mask(scl)

    expected = np.array([[True, False], [False, True], [True, True]], dtype=bool)
    np.testing.assert_array_equal(invalid_mask, expected)
