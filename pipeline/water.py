"""Water extraction module: raster reading, NDWI calculation, and SCL cloud masking.

Data credits: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search).
"""

from __future__ import annotations

from typing import Tuple
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds

# SCL invalid classes per Sentinel-2 L2A specification:
# 0: NO_DATA, 1: SATURATED_OR_DEFECTIVE, 3: CLOUD_SHADOWS,
# 8: CLOUD_MEDIUM_PROBABILITY, 9: CLOUD_HIGH_PROBABILITY, 10: THIN_CIRRUS
DEFAULT_INVALID_SCL = (0, 1, 3, 8, 9, 10)
DEFAULT_NDWI_THRESHOLD = 0.05


def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Compute Normalized Difference Water Index (NDWI) = (Green - NIR) / (Green + NIR).

    Input arrays are expected to be float or converted to float32.
    """
    g = green.astype(np.float32)
    n = nir.astype(np.float32)
    denom = g + n
    denom[denom == 0] = 1e-6
    ndwi = (g - n) / denom
    return ndwi


def get_scl_invalid_mask(
    scl: np.ndarray, invalid_classes: Tuple[int, ...] = DEFAULT_INVALID_SCL
) -> np.ndarray:
    """Return a boolean mask where True indicates invalid pixels (clouds, shadows, no-data)."""
    return np.isin(scl, invalid_classes)


def read_scene_bands(
    green_url: str,
    nir_url: str,
    scl_url: str,
    bbox: list[float],
    ndwi_threshold: float = DEFAULT_NDWI_THRESHOLD,
    invalid_scl: Tuple[int, ...] = DEFAULT_INVALID_SCL,
) -> dict:
    """Read Green (B03), NIR (B08), and SCL bands for a WGS84 bounding box from S3 COGs over HTTPS.

    Resamples SCL (20m) to match the 10m Green/NIR raster window.

    Returns dict containing:
        ndwi: 2D float32 array
        water_mask: 2D bool array (ndwi > ndwi_threshold)
        scl_invalid_mask: 2D bool array
        scl: 2D array
        transform: Affine window transform
        crs: Raster CRS
        shape: (height, width)
        pixel_area_ha: 0.01 (ha per 10m x 10m pixel)
    """
    with rasterio.open(green_url) as g_src, rasterio.open(nir_url) as n_src, rasterio.open(scl_url) as s_src:
        # Transform WGS84 bbox coordinates to raster CRS (UTM)
        left, bottom, right, top = transform_bounds("EPSG:4326", g_src.crs, *bbox)

        # Build window for green band (10m)
        g_win = rasterio.windows.from_bounds(left, bottom, right, top, transform=g_src.transform)
        # Round window to integer pixel offsets
        g_win = g_win.round_offsets()
        g_win_transform = rasterio.windows.transform(g_win, g_src.transform)

        green = g_src.read(1, window=g_win).astype(np.float32)

        # Read NIR band with matching window shape
        n_win = rasterio.windows.from_bounds(left, bottom, right, top, transform=n_src.transform).round_offsets()
        nir = n_src.read(1, window=n_win, out_shape=green.shape, resampling=Resampling.bilinear).astype(np.float32)

        # Read SCL band (20m) resampled to 10m matching green array shape
        s_win = rasterio.windows.from_bounds(left, bottom, right, top, transform=s_src.transform).round_offsets()
        scl = s_src.read(1, window=s_win, out_shape=green.shape, resampling=Resampling.nearest)

        ndwi = compute_ndwi(green, nir)
        water_mask = ndwi > ndwi_threshold
        scl_invalid = get_scl_invalid_mask(scl, invalid_classes=invalid_scl)

        # Calculate pixel resolution and area in hectares
        # For 10m pixel, resolution is ~10m x 10m = 100 m^2 = 0.01 ha
        res_x = abs(g_win_transform.a)
        res_y = abs(g_win_transform.e)
        pixel_area_ha = (res_x * res_y) / 10000.0

        return {
            "ndwi": ndwi,
            "water_mask": water_mask,
            "scl_invalid_mask": scl_invalid,
            "scl": scl,
            "transform": g_win_transform,
            "crs": g_src.crs,
            "shape": green.shape,
            "pixel_area_ha": pixel_area_ha,
        }
