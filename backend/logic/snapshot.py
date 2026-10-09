"""measurements.json (pipeline output) -> ponds.json snapshot as of date T. Pure, no I/O.

Honest backtest: every input is cut at T (scenes, pond histories, observed ET0). The only
look-ahead is "expected heat", taken from the forecast (live) or the 2019-2023 climatology
(replay), both of which were knowable at T.
"""
from __future__ import annotations

from datetime import date, timedelta

from logic.countdown import WINDOW_DAYS, countdown, fit_window
from logic.flags import faster_than_sun, sun_share_mm

EXPECT_DAYS = 30


def _d(s: str | date) -> date:
    return s if isinstance(s, date) else date.fromisoformat(s)


def mean_et0(series: list[dict], start: date, end: date) -> float | None:
    vals = [float(x["et0"]) for x in series if x.get("et0") is not None and start <= _d(x["date"]) <= end]
    return sum(vals) / len(vals) if vals else None


def expected_et0(meas: dict, as_of: date) -> float | None:
    """Mean ET0 expected over the next 30 days: forecast where available, else climatology."""
    start, end = as_of + timedelta(days=1), as_of + timedelta(days=EXPECT_DAYS)
    forecast = mean_et0(meas.get("et0Forecast") or [], start, end)
    if forecast is not None:
        return forecast
    clim = meas.get("et0Climatology") or {}
    vals = []
    for i in range(EXPECT_DAYS):
        day = start + timedelta(days=i)
        key = day.strftime("%m-%d")
        v = clim.get(key, clim.get("02-28") if key == "02-29" else None)
        if v is not None:
            vals.append(float(v))
    return sum(vals) / len(vals) if vals else None


def build_snapshot(meas: dict, as_of: str | date) -> dict:
    t = _d(as_of)
    start, end = fit_window(t, WINDOW_DAYS)
    observed = [x for x in meas.get("et0", []) if _d(x["date"]) <= t]
    fit_mean = mean_et0(observed, start, end)
    exp_mean = expected_et0(meas, t)

    rows = []
    for p in meas["ponds"]:
        hist = sorted((h for h in p["history"] if _d(h["date"]) <= t), key=lambda h: h["date"])
        c = countdown(hist, t, exp_mean, fit_mean)
        rows.append((p, hist, c))

    flags = faster_than_sun(
        [{"id": p["id"], "slopeHaPerDay": c["slopeHaPerDay"], "maxAreaHa": c["maxAreaHa"], "status": c["status"],
          "lat": p.get("lat"), "lon": p.get("lon")} for p, _, c in rows]
    )

    ponds = []
    for p, hist, c in rows:
        ponds.append(
            {
                "id": p["id"],
                "lat": p["lat"],
                "lon": p["lon"],
                "place": p.get("place", ""),
                **({"placeMr": p["placeMr"]} if p.get("placeMr") else {}),
                "maxAreaHa": c["maxAreaHa"] if c["maxAreaHa"] is not None else p.get("refAreaHa"),
                "areaNowHa": c["areaNowHa"],
                "history": hist,
                "dryBy": c["dryBy"],
                "daysLeft": c["daysLeft"],
                "shrinkVsNeighbours": flags[p["id"]]["shrinkVsNeighbours"],
                "flag": flags[p["id"]]["flag"],
                "status": c["status"],
            }
        )

    doc = {
        "region": meas["region"],
        "asOf": t.isoformat(),
        "sunShareMm": sun_share_mm(observed, start, end),
        "scenes": [s for s in meas["scenes"] if _d(s["date"]) <= t],
        "ponds": sorted(ponds, key=lambda p: p["id"]),
    }
    if meas.get("excludedPonds"):  # detections dropped by the pipeline's quality rules, with reasons
        doc["excludedPonds"] = meas["excludedPonds"]
    return doc
