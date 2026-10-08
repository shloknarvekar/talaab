import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from synth_measurements import generate  # noqa: E402

from logic.snapshot import build_snapshot, expected_et0  # noqa: E402

MEAS = generate()


def by_id(snap):
    return {p["id"]: p for p in snap["ponds"]}


def test_snapshot_never_uses_data_after_as_of():
    snap = build_snapshot(MEAS, "2024-03-26")
    assert snap["asOf"] == "2024-03-26"
    assert all(s["date"] <= "2024-03-26" for s in snap["scenes"])
    assert all(h["date"] <= "2024-03-26" for p in snap["ponds"] for h in p["history"])
    # changing the future must not change the past snapshot
    future = generate()
    for p in future["ponds"]:
        for h in p["history"]:
            if h["date"] > "2024-03-26":
                h["areaHa"] = 999.0
    assert build_snapshot(future, "2024-03-26") == snap


def test_snapshot_matches_contract_shape():
    snap = build_snapshot(MEAS, "2024-04-10")
    assert set(snap) == {"region", "asOf", "sunShareMm", "scenes", "ponds"}
    keys = {"id", "lat", "lon", "place", "maxAreaHa", "areaNowHa", "history", "dryBy", "daysLeft",
            "shrinkVsNeighbours", "flag", "status"}
    assert all(set(p) == keys for p in snap["ponds"])
    assert snap["sunShareMm"] > 0


def test_pumped_pond_flagged_small_one_not():
    snap = by_id(build_snapshot(MEAS, "2024-04-10"))
    assert snap["P003"]["flag"] == "faster-than-sun"
    assert snap["P013"]["flag"] is None  # pumped but under 2 ha
    assert snap["P001"]["flag"] is None


def test_season_gets_drier():
    def n_dry_or_critical(d):
        return sum(p["status"] in ("dry", "critical") for p in build_snapshot(MEAS, d)["ponds"])

    assert n_dry_or_critical("2024-02-20") < n_dry_or_critical("2024-04-20") < n_dry_or_critical("2024-06-04")


def test_spring_fed_pond_is_stable():
    p = by_id(build_snapshot(MEAS, "2024-05-01"))["P014"]
    assert p["status"] == "ok" and p["dryBy"] is None


def test_too_early_is_unknown():
    snap = build_snapshot(MEAS, "2024-01-21")  # only two passes so far
    assert all(p["status"] == "unknown" for p in snap["ponds"])


def test_expected_heat_prefers_forecast_over_climatology():
    t = date(2024, 3, 26)
    clim = expected_et0(MEAS, t)
    assert 5.0 < clim < 8.5  # late-March/April climatology
    live = {**MEAS, "et0Forecast": [{"date": f"2024-04-{d:02d}", "et0": 9.0} for d in range(1, 26)]}
    assert expected_et0(live, t) == pytest.approx(9.0)
