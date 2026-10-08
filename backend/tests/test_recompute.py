"""Recompute job against a local data folder, fake weather and a fake table (no network, no AWS)."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from synth_measurements import generate  # noqa: E402

from api import store  # noqa: E402
from jobs import recompute  # noqa: E402
from jobs.weather import merge_observed, recent_and_forecast  # noqa: E402

TODAY = date(2024, 6, 16)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    for region in ("latur-2024-synthetic", "latur-2026"):
        d = tmp_path / region
        d.mkdir()
        (d / "measurements.json").write_text(json.dumps(generate()), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PONDS_TABLE", raising=False)
    store.clear_cache()
    yield tmp_path
    store.clear_cache()


def fake_weather(lat, lon, today):
    observed = [{"date": (today - timedelta(days=i)).isoformat(), "et0": 6.0, "precip": 0.0} for i in range(60)]
    forecast = [{"date": (today + timedelta(days=i)).isoformat(), "et0": 9.0, "precip": 0.0} for i in range(1, 17)]
    return observed, forecast


def broken_weather(lat, lon, today):
    raise TimeoutError("open-meteo down")


def test_replay_region_builds_every_snapshot_and_index(data_dir):
    rows = []
    out = recompute.recompute_region("latur-2024-synthetic", TODAY, fetch_weather=fake_weather,
                                     write_table=lambda r, s: rows.append((r, s["asOf"])) or len(s["ponds"]))
    assert out["snapshots"] == 27 and out["latestAsOf"] == "2024-06-14" and out["forecastDays"] == 0
    index = json.loads((data_dir / "latur-2024-synthetic" / "index.json").read_text(encoding="utf-8"))
    assert len(index["asOf"]) == 27 and index["mode"] == "replay"
    assert rows == [("latur-2024-synthetic", "2024-06-14")] and out["dynamoRows"] == 14


def test_live_region_adds_today_with_forecast_only_today(data_dir):
    out = recompute.recompute_region("latur-2026", TODAY, fetch_weather=fake_weather, write_table=lambda r, s: 0)
    assert out["latestAsOf"] == TODAY.isoformat() and out["forecastDays"] == 16
    today_snap = json.loads((data_dir / "latur-2026" / "asof" / f"{TODAY}.json").read_text(encoding="utf-8"))
    assert today_snap["live"] is True and today_snap["region"]["name"] == "Latur (live, 2026)"
    # the hotter forecast only affects today's snapshot; past snapshots match the pure replay
    past = json.loads((data_dir / "latur-2026" / "asof" / "2024-06-14.json").read_text(encoding="utf-8"))
    replay_past = recompute.build_snapshot(generate(), "2024-06-14")
    assert [p["status"] for p in past["ponds"]] == [p["status"] for p in replay_past["ponds"]]


def test_handler_isolates_failures_and_skips_missing(data_dir, monkeypatch):
    original = recompute.recompute_region
    monkeypatch.setattr(recompute, "recompute_region",
                        lambda region, today: original(region, today, fetch_weather=broken_weather, write_table=lambda r, s: 0))
    out = recompute.lambda_handler({"today": TODAY.isoformat()}, None)
    by_region = {r["region"]: r for r in out["results"]}
    assert "skipped" in by_region["latur-2024"]  # nothing uploaded for the real replay yet
    assert by_region["latur-2024-synthetic"]["snapshots"] == 27  # replay needs no weather call
    assert "TimeoutError" in by_region["latur-2026"]["error"]  # weather failure isolated to the live region


def test_unknown_region_reported():
    out = recompute.lambda_handler({"regions": ["mars-2030"], "today": "2024-06-16"}, None)
    assert out["results"] == [{"region": "mars-2030", "error": "unknown region"}]


def test_weather_parsing_and_merge():
    payload = {"daily": {"time": ["2026-10-07", "2026-10-08", "2026-10-09"],
                         "et0_fao_evapotranspiration": [4.5, None, 5.1],
                         "precipitation_sum": [0.0, 1.0, 0.0]}}
    seen = []
    obs, fc = recent_and_forecast(18.4, 76.5, date(2026, 10, 8), get_json=lambda url: seen.append(url) or payload)
    assert obs == [{"date": "2026-10-07", "et0": 4.5, "precip": 0.0}]
    assert fc == [{"date": "2026-10-09", "et0": 5.1, "precip": 0.0}]
    assert "past_days=60" in seen[0] and "forecast_days=16" in seen[0]
    merged = merge_observed([{"date": "2026-10-07", "et0": 4.0, "precip": 0.0}],
                            obs + [{"date": "2026-10-08", "et0": 4.8, "precip": 0}])
    assert merged == [{"date": "2026-10-07", "et0": 4.0, "precip": 0.0}, {"date": "2026-10-08", "et0": 4.8, "precip": 0}]


def test_api_serves_recomputed_region(data_dir):
    from api import handler

    recompute.recompute_region("latur-2024-synthetic", TODAY, write_table=lambda r, s: 0)
    store.clear_cache()
    r = handler.lambda_handler({"routeKey": "GET /ponds", "queryStringParameters": {"region": "latur-2024-synthetic", "asOf": "2024-04-12"}}, None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 200 and body["asOf"] == "2024-04-10" and len(body["ponds"]) == 14
