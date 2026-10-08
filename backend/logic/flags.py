"""The "faster than the sun" flag. Pure functions, no I/O, no AWS.

METHOD (see CLAUDE.md):
- Relative shrink rate r = -slope / A_ref per day (A_ref = pond's max/reference area).
- Compare each pond to the median r of the region's SHRINKING (non-dry, r > 0) ponds over the same
  window; with fewer than 3 such peers there is no baseline and no flag.
- Flag if ratio >= 2 and A_ref >= 2 ha.
- Report the region's ET0 total for that window as "the sun's share".
"""
from __future__ import annotations

from datetime import date
from statistics import median

FLAG = "faster-than-sun"
RATIO_THRESHOLD = 2.0
MIN_AREA_HA = 2.0
MIN_PEERS = 3  # need at least 3 shrinking ponds to say what 'normal under this sun' is


def relative_shrink_rate(slope_ha_per_day: float, a_ref_ha: float) -> float:
    """Fraction of the pond lost per day (positive = shrinking)."""
    if a_ref_ha <= 0:
        raise ValueError("a_ref_ha must be positive")
    return -slope_ha_per_day / a_ref_ha


def faster_than_sun(
    ponds: list[dict],
    ratio_threshold: float = RATIO_THRESHOLD,
    min_area_ha: float = MIN_AREA_HA,
) -> dict[str, dict]:
    """Compare every pond's shrink rate to its neighbours under the same sun.

    ponds: [{"id", "slopeHaPerDay" (None if not fitted), "maxAreaHa", "status"}],
    all fitted over the same window (output of countdown()).
    Returns {id: {"shrinkVsNeighbours": float|None, "flag": "faster-than-sun"|None}}.
    """
    rates: dict[str, float] = {}
    for p in ponds:
        if p.get("slopeHaPerDay") is None or not p.get("maxAreaHa"):
            continue
        rates[p["id"]] = relative_shrink_rate(p["slopeHaPerDay"], p["maxAreaHa"])

    # Baseline = median rate of ponds that are actually shrinking (not dry, r > 0). Including
    # stable tanks drags the median toward zero late in the season, and then every normally
    # shrinking pond looks "13x faster" (seen on the real 2024 data). Too few peers: no flags.
    baseline_rates = [rates[p["id"]] for p in ponds if p["id"] in rates and p.get("status") != "dry" and rates[p["id"]] > 0]
    baseline = median(baseline_rates) if len(baseline_rates) >= MIN_PEERS else None

    out: dict[str, dict] = {}
    for p in ponds:
        r = rates.get(p["id"])
        if r is None or baseline is None or baseline <= 0 or p.get("status") == "dry":
            out[p["id"]] = {"shrinkVsNeighbours": None, "flag": None}
            continue
        ratio = r / baseline
        flagged = ratio >= ratio_threshold and p["maxAreaHa"] >= min_area_ha
        out[p["id"]] = {"shrinkVsNeighbours": round(ratio, 2), "flag": FLAG if flagged else None}
    return out


def sun_share_mm(et0_daily: list[dict], start: date | str, end: date | str) -> float:
    """Total ET0 (mm) over [start, end] inclusive. et0_daily: [{"date": "YYYY-MM-DD", "et0": mm}]."""
    s = start if isinstance(start, date) else date.fromisoformat(start)
    e = end if isinstance(end, date) else date.fromisoformat(end)
    total = sum(
        float(d["et0"])
        for d in et0_daily
        if d.get("et0") is not None and s <= date.fromisoformat(d["date"]) <= e
    )
    return round(total, 1)
