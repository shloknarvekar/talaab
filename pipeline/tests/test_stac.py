"""Tests for pipeline/stac.py STAC scene discovery module."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from pipeline.stac import STACScene, search_scenes


def test_stac_scene_dataclass():
    scene = STACScene(
        id="S2B_43QFA_20240116_0_L2A",
        date="2024-01-16",
        datetime_utc=MagicMock(),
        cloud_cover=2.5,
        green_url="https://example.com/green.tif",
        nir_url="https://example.com/nir.tif",
        scl_url="https://example.com/scl.tif",
        visual_url="https://example.com/visual.tif",
    )
    assert scene.id == "S2B_43QFA_20240116_0_L2A"
    assert scene.date == "2024-01-16"
    assert scene.cloud_cover == 2.5


@patch("pystac_client.Client.open")
def test_search_scenes_deduplication(mock_open):
    # Mock item 1 (43QFA tile)
    item1 = MagicMock()
    item1.id = "S2B_43QFA_20240116_0_L2A"
    item1.datetime = datetime(2024, 1, 16, 5, 30)
    item1.properties = {"datetime": "2024-01-16T05:30:00Z", "eo:cloud_cover": 5.0}
    item1.assets = {
        "green": MagicMock(href="http://example.com/green.tif"),
        "nir": MagicMock(href="http://example.com/nir.tif"),
        "scl": MagicMock(href="http://example.com/scl.tif"),
        "visual": MagicMock(href="http://example.com/visual.tif"),
    }

    # Mock item 2 (same date, non-43QFA tile, higher cloud)
    item2 = MagicMock()
    item2.id = "S2B_43QFB_20240116_0_L2A"
    item2.datetime = datetime(2024, 1, 16, 5, 35)
    item2.properties = {"datetime": "2024-01-16T05:35:00Z", "eo:cloud_cover": 15.0}
    item2.assets = item1.assets

    mock_client = MagicMock()
    mock_client.search.return_value.items.return_value = [item1, item2]
    mock_open.return_value = mock_client

    scenes = search_scenes(bbox=[76.47, 18.33, 76.62, 18.48], start_date="2024-01-01", end_date="2024-01-31")

    # Should deduplicate to single scene for 2024-01-16 (preferring 43QFA tile)
    assert len(scenes) == 1
    assert scenes[0].id == "S2B_43QFA_20240116_0_L2A"
    assert scenes[0].date == "2024-01-16"
