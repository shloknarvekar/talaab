import random
from datetime import date, timedelta

import pytest

from logic.countdown import countdown, linear_fit, et0_scale, usable_points

AS_OF = date(2024, 3, 26)


def series(start_area, slope, days=70, step=5, noise=0.0, seed=1, end=AS_OF):
    """Synthetic pass history ending at `end`, one pass every `step` days."""
    rng = random.Random(seed)
    out = []
    first = end - timedelta(days=days)
    for i in range(0, days + 1, step):
        d = first + timedelta(days=i)
        a = start_area + slope * i + (rng.uniform(-noise, noise) if noise else 0.0)
        out.append({"date": d.isoformat(), "areaHa": round(max(a, 0.0), 3), "valid": True})
    return out


def test_steady_shrink_exact_maths():
    # 50 ha shrinking 0.5 ha/day for 70 days -> 15 ha now, max 50, dry at 2.5 ha
    c = countdown(series(50.0, -0.5), AS_OF)
    assert c["trend"] == "shrinking"
    assert c["areaNowHa"] == 15.0 and c["maxAreaHa"] == 50.0
    assert c["slopeHaPerDay"] == pytest.approx(-0.5)
    assert c["slopeSe"] == pytest.approx(0.0, abs=1e-9)
    # (15 - 2.5) / 0.5 = 25 days; perfect fit -> range is the +/-20% floor
    assert c["daysLeft"] == {"min": 20, "likely": 25, "max": 30}
    assert c["dryBy"] == {"earliest": "2024-04-15", "likely": "2024-04-20", "latest": "2024-04-25"}
    assert c["status"] == "critical"


def test_hotter_month_ahead_brings_date_forward():
    # next 30 days expected 1.25x hotter than the fit window -> 25 / 1.25 = 20 days
    c = countdown(series(50.0, -0.5), AS_OF, et0_expected_next30=6.25, et0_fit_window=5.0)
    assert c["daysLeft"]["likely"] == 20
    assert et0_scale(None, 5.0) == 1.0 and et0_scale(6.0, 0) == 1.0


def test_status_bands():
    # now 32 ha, max 60 -> (32 - 3) / 0.4 = 72.5 days -> watch
    assert countdown(series(60.0, -0.4), AS_OF)["status"] == "watch"
    # now 72 ha, max 100 -> (72 - 5) / 0.4 = 167.5 days -> ok
    assert countdown(series(100.0, -0.4), AS_OF)["status"] == "ok"


def test_stable_pond():
    c = countdown(series(20.0, 0.0), AS_OF)
    assert c["trend"] == "stable" and c["status"] == "ok"
    assert c["dryBy"] is None and c["daysLeft"] is None
    assert countdown(series(20.0, +0.05), AS_OF)["trend"] == "stable"


def test_noisy_pond_gives_wider_range_that_brackets_likely():
    clean = countdown(series(40.0, -0.3), AS_OF)
    noisy = countdown(series(40.0, -0.3, noise=2.0, seed=3), AS_OF)
    assert noisy["trend"] == "shrinking"
    assert noisy["slopeSe"] > 0
    d, c = noisy["daysLeft"], clean["daysLeft"]
    assert d["min"] < d["likely"] < d["max"]
    assert (d["max"] - d["min"]) / d["likely"] > (c["max"] - c["min"]) / c["likely"]
    # never tighter than +/-20% (allowing for day rounding)
    assert d["min"] <= 0.8 * d["likely"] + 1 and d["max"] >= 1.2 * d["likely"] - 1


def test_too_few_points_is_unknown():
    h = [
        {"date": "2024-01-10", "areaHa": 30.0, "valid": True},  # outside the 45-day window
        {"date": "2024-03-01", "areaHa": 25.0, "valid": True},
        {"date": "2024-03-21", "areaHa": 22.0, "valid": True},
    ]
    c = countdown(h, AS_OF)
    assert c["status"] == "unknown" and c["trend"] == "insufficient"
    assert c["dryBy"] is None and c["daysLeft"] is None
    assert c["nPoints"] == 2
    assert countdown([], AS_OF)["status"] == "unknown"


def test_invalid_points_are_ignored():
    h = series(50.0, -0.5)
    for i in (-2, -4, -6):  # cloud-contaminated spikes, marked invalid by cleanup
        h[i]["areaHa"], h[i]["valid"] = 500.0, False
    c = countdown(h, AS_OF)
    assert c["maxAreaHa"] == 50.0
    assert c["slopeHaPerDay"] == pytest.approx(-0.5)


def test_backtest_never_peeks_past_as_of():
    h = series(50.0, -0.5)
    future = h + [{"date": "2024-04-10", "areaHa": 80.0, "valid": True}]
    assert countdown(future, AS_OF) == countdown(h, AS_OF)
    earlier = date(2024, 3, 1)
    assert all(d <= earlier for d, _ in usable_points(future, earlier))


def test_dry_pond():
    c = countdown(series(6.0, -0.09), AS_OF)  # 6 - 6.3 -> 0 ha now
    assert c["status"] == "dry" and c["trend"] == "dry"
    assert c["daysLeft"] == {"min": 0, "likely": 0, "max": 0}
    assert c["dryBy"] is None


def test_very_slow_shrink_is_capped():
    c = countdown(series(100.0, -0.01), AS_OF)
    assert c["daysLeft"]["likely"] <= 365 and c["daysLeft"]["max"] <= 365
    assert c["status"] == "ok"


def test_linear_fit_needs_three_points():
    with pytest.raises(ValueError):
        linear_fit([(date(2024, 1, 1), 1.0), (date(2024, 1, 2), 2.0)])
