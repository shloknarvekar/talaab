"""Sentinel-2 L2A scene discovery via Element 84 Earth Search STAC API.

Data credits: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
import pystac_client

# Set GDAL / AWS S3 environment variables for fast COG reading over HTTPS
os.environ["AWS_NO_SIGN_REQUEST"] = "YES"
os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"

EARTH_SEARCH_API = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
DEFAULT_BBOX = [76.47, 18.33, 76.62, 18.48]  # Latur district bbox


@dataclass
class STACScene:
    id: str
    date: str  # YYYY-MM-DD
    datetime_utc: datetime
    cloud_cover: float
    green_url: str
    nir_url: str
    scl_url: str
    visual_url: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "cloudCover": round(self.cloud_cover, 2),
            "greenUrl": self.green_url,
            "nirUrl": self.nir_url,
            "sclUrl": self.scl_url,
            "visualUrl": self.visual_url,
        }


def search_scenes(
    bbox: list[float] = DEFAULT_BBOX,
    start_date: str = "2024-01-01",
    end_date: str = "2024-06-30",
    max_cloud_cover: float = 20.0,
    stac_url: str = EARTH_SEARCH_API,
) -> list[STACScene]:
    """Search Earth Search STAC API for Sentinel-2 L2A scenes matching bbox and date range.

    Returns scenes sorted oldest first by date. Deduplicates scenes by date (taking lowest cloud cover).
    """
    catalog = pystac_client.Client.open(stac_url)
    date_range = f"{start_date}/{end_date}"

    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": max_cloud_cover}},
    )

    items = list(search.items())

    # Map dates to best scene (lowest cloud cover, preferring 43QFA tile if matching)
    scenes_by_date: dict[str, STACScene] = {}

    for item in items:
        dt = item.datetime
        date_str = dt.strftime("%Y-%m-%d")
        cc = float(item.properties.get("eo:cloud_cover", 0.0))

        # Extract asset URLs
        green_href = _get_asset_href(item, ["green", "B03", "green-jp2"])
        nir_href = _get_asset_href(item, ["nir", "B08", "nir-jp2"])
        scl_href = _get_asset_href(item, ["scl", "SCL", "scl-jp2"])
        visual_href = _get_asset_href(item, ["visual", "visual-jp2"], required=False)

        if not (green_href and nir_href and scl_href):
            continue

        scene = STACScene(
            id=item.id,
            date=date_str,
            datetime_utc=dt,
            cloud_cover=cc,
            green_url=green_href,
            nir_url=nir_href,
            scl_url=scl_href,
            visual_url=visual_href,
        )

        if date_str not in scenes_by_date:
            scenes_by_date[date_str] = scene
        else:
            existing = scenes_by_date[date_str]
            # Prefer tile 43QFA or lower cloud cover
            if "43QFA" in scene.id and "43QFA" not in existing.id:
                scenes_by_date[date_str] = scene
            elif cc < existing.cloud_cover:
                scenes_by_date[date_str] = scene

    # Sort oldest first by date
    sorted_scenes = sorted(scenes_by_date.values(), key=lambda s: s.date)
    return sorted_scenes


def _get_asset_href(item, keys: list[str], required: bool = True) -> str | None:
    for k in keys:
        if k in item.assets:
            return item.assets[k].href
    if required:
        raise KeyError(f"Asset key matching {keys} not found in STAC item {item.id}")
    return None


if __name__ == "__main__":
    print("Testing STAC discovery for 2024 replay...")
    scenes_2024 = search_scenes(start_date="2024-01-01", end_date="2024-06-30")
    print(f"Found {len(scenes_2024)} scenes for 2024:")
    for s in scenes_2024:
        print(f"  {s.date} | {s.id} | cloud: {s.cloud_cover:.1f}%")
