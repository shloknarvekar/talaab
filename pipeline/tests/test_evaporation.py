"""Tests for pipeline/evaporation.py weather and climatology module."""

from unittest.mock import MagicMock, patch

from pipeline.evaporation import fetch_climatology_2019_2023, fetch_daily_weather


@patch("pipeline.evaporation.requests.get")
def test_fetch_daily_weather(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "daily": {
            "time": ["2024-01-16", "2024-01-17"],
            "et0_fao_evapotranspiration": [3.5, 4.2],
            "precipitation_sum": [0.0, 12.5],
        }
    }
    mock_get.return_value = mock_resp

    res = fetch_daily_weather("2024-01-16", "2024-01-17", use_cache=False)
    assert len(res) == 2
    assert res[0] == {"date": "2024-01-16", "et0": 3.5, "precip": 0.0}
    assert res[1] == {"date": "2024-01-17", "et0": 4.2, "precip": 12.5}


@patch("pipeline.evaporation.requests.get")
def test_fetch_climatology_2019_2023(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "daily": {
            "time": ["2019-01-01", "2020-01-01", "2019-02-28", "2019-03-01"],
            "et0_fao_evapotranspiration": [3.0, 4.0, 5.0, 5.2],
        }
    }
    mock_get.return_value = mock_resp

    clim = fetch_climatology_2019_2023(use_cache=False)
    assert "01-01" in clim
    assert np_isclose(clim["01-01"], 3.5)
    assert "02-29" in clim  # Leap day interpolated


def np_isclose(a, b):
    return abs(a - b) < 1e-5
