"""Per-pond "dry-by" countdown. Pure functions, no I/O, no AWS.

METHOD (see CLAUDE.md):
- Use valid points in the last 45 days up to as-of date T (needs >= 3 points).
- Linear fit of area vs time. slope >= 0 -> "stable" (also when the shrink is within
  2 standard errors of zero, or the pond would last more than a year).
- Else days to reach 5% of max area = (A_now - 0.05*A_max) / |slope|, with the
  slope scaled by (expected mean ET0 next 30 days / mean ET0 in the fit window).
- Range from slope +/- its standard error, widened to at least +/-20%.
- Status: dry (< 5% of max), critical (< 30 d), watch (30-90 d), ok (> 90 d or stable).

Only points dated <= T are ever used, so a replay at T is an honest backtest.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

WINDOW_DAYS = 45
MIN_POINTS = 3
DRY_FRACTION = 0.05
MIN_RANGE_FRACTION = 0.20
MAX_DAYS = 365  # cap so "latest" is always a real date; likely >= this counts as stable
STABLE_SE_MULTIPLE = 2.0  # shrink smaller than 2 standard errors = noise
CRITICAL_DAYS = 30
WATCH_DAYS = 90


@dataclass(frozen=True)
class Fit:
    slope: float  # ha per day
    slope_se: float  # standard error of the slope
    n: int


def _as_date(d: date | str) -> date:
    return d if isinstance(d, date) else date.fromisoformat(d)


def fit_window(as_of: date | str, window_days: int = WINDOW_DAYS) -> tuple[date, date]:
    """Inclusive [start, end] dates of the fit window ending at as_of."""
    end = _as_date(as_of)
    return end - timedelta(days=window_days), end


def usable_points(history: list[dict], as_of: date | str, window_days: int = WINDOW_DAYS) -> list[tuple[date, float]]:
    """Valid (date, areaHa) points inside the window, sorted by date. Never looks past as_of."""
    start, end = fit_window(as_of, window_days)
    pts = [
        (_as_date(h["date"]), float(h["areaHa"]))
        for h in history
        if h.get("valid", True) and start <= _as_date(h["date"]) <= end
    ]
    return sorted(pts)


def linear_fit(points: list[tuple[date, float]]) -> Fit:
    """Ordinary least squares of area vs day number. Needs >= 3 points for a standard error."""
    n = len(points)
    if n < 3:
        raise ValueError("need at least 3 points")
    t0 = points[0][0]
    xs = [(d - t0).days for d, _ in points]
    ys = [a for _, a in points]
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("points must span more than one date")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    ssr = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(ssr / (n - 2) / sxx)
    return Fit(slope=slope, slope_se=se, n=n)


def et0_scale(expected_mean_next30: float | None, fit_window_mean: float | None) -> float:
    """Heat adjustment: >1 when the coming month is expected to be hotter than the fit window."""
    if not expected_mean_next30 or not fit_window_mean or expected_mean_next30 <= 0 or fit_window_mean <= 0:
        return 1.0
    return expected_mean_next30 / fit_window_mean


def status_for(days_likely: float | None, is_dry: bool) -> str:
    if is_dry:
        return "dry"
    if days_likely is None:
        return "ok"
    if days_likely < CRITICAL_DAYS:
        return "critical"
    if days_likely <= WATCH_DAYS:
        return "watch"
    return "ok"


def _days_to(remaining: float, rate: float) -> float:
    if rate <= 0:
        return float(MAX_DAYS)
    return min(remaining / rate, float(MAX_DAYS))


def countdown(
    history: list[dict],
    as_of: date | str,
    et0_expected_next30: float | None = None,
    et0_fit_window: float | None = None,
) -> dict:
    """Countdown for one pond as of date T.

    history: contract items {"date": "YYYY-MM-DD", "areaHa": float, "valid": bool}.
    et0_*: mean daily ET0 (mm) expected for the next 30 days / observed in the fit window.

    Returns keys: trend ("shrinking"|"stable"|"insufficient"|"dry"), status,
    maxAreaHa, areaNowHa, slopeHaPerDay, slopeSe, nPoints, daysLeft, dryBy.
    status is "unknown" when there is too little data to say anything.
    """
    t = _as_date(as_of)
    past_valid = sorted(
        (_as_date(h["date"]), float(h["areaHa"]))
        for h in history
        if h.get("valid", True) and _as_date(h["date"]) <= t
    )
    out = {
        "trend": "insufficient",
        "status": "unknown",
        "maxAreaHa": None,
        "areaNowHa": None,
        "slopeHaPerDay": None,
        "slopeSe": None,
        "nPoints": 0,
        "daysLeft": None,
        "dryBy": None,
    }
    if not past_valid:
        return out

    a_max = max(a for _, a in past_valid)
    a_now = past_valid[-1][1]
    out["maxAreaHa"] = round(a_max, 2)
    out["areaNowHa"] = round(a_now, 2)

    if a_now < DRY_FRACTION * a_max:
        out.update(trend="dry", status="dry", daysLeft={"min": 0, "likely": 0, "max": 0})
        return out

    pts = usable_points(history, t)
    out["nPoints"] = len(pts)
    if len(pts) < MIN_POINTS or len({d for d, _ in pts}) < 2:
        return out

    fit = linear_fit(pts)
    out["slopeHaPerDay"] = round(fit.slope, 4)
    out["slopeSe"] = round(fit.slope_se, 4)

    # Stable: not shrinking, or the shrink is within measurement noise (slope + 2 SE >= 0).
    # Without the noise test a spring-fed pond gets a fake "dry in 300 days" from jitter alone.
    if fit.slope >= 0 or fit.slope + STABLE_SE_MULTIPLE * fit.slope_se >= 0:
        out.update(trend="stable", status="ok")
        return out

    scale = et0_scale(et0_expected_next30, et0_fit_window)
    rate = -fit.slope * scale
    rate_fast = (-fit.slope + fit.slope_se) * scale
    rate_slow = (-fit.slope - fit.slope_se) * scale
    remaining = a_now - DRY_FRACTION * a_max

    likely = _days_to(remaining, rate)
    if likely >= MAX_DAYS:  # would last more than a year: no dry-by date to promise
        out.update(trend="stable", status="ok")
        return out
    earliest = min(_days_to(remaining, rate_fast), likely * (1 - MIN_RANGE_FRACTION))
    latest = min(max(_days_to(remaining, rate_slow), likely * (1 + MIN_RANGE_FRACTION)), float(MAX_DAYS))

    days = {
        "min": int(math.floor(earliest)),
        "likely": int(round(likely)),
        "max": int(math.ceil(latest)),
    }
    out.update(
        trend="shrinking",
        status=status_for(likely, is_dry=False),
        daysLeft=days,
        dryBy={
            "earliest": (t + timedelta(days=days["min"])).isoformat(),
            "likely": (t + timedelta(days=days["likely"])).isoformat(),
            "latest": (t + timedelta(days=days["max"])).isoformat(),
        },
    )
    return out
