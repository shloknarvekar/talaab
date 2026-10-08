"""Cleanup and quality assurance module.

Scene level: a pass is "suspect" when the region's total water area is far from its neighbouring
passes (up without rain, or down at all: evaporation cannot remove 40% of a district's water in
a few days). Every pond reading on a suspect pass is marked invalid.

Pond level: single-pass spikes AND dips are marked invalid. Ponds that were not really there
(water on the reference date only) or whose water signal is erratic are excluded, with a reason.

Data credits: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search).
"""

from __future__ import annotations

from datetime import date
from statistics import median
from typing import Dict, List, Tuple

SUSPECT_JUMP = 0.40          # region total differs >40% from its neighbours
NEIGHBOURS = 2               # passes on each side used for the neighbour median
MIN_DIP_HA = 0.3             # a dip/recovery must be at least this big to count (tiny-pond noise)
PRESENCE_WINDOW_DAYS = 15    # look this far around the reference date to confirm a pond exists
PRESENCE_SHARE = 0.5         # ...and require water >= 50% of reference area on half those passes
ERRATIC_DEVIATION = 0.40     # a reading > 40% of reference area away from its neighbours' mean
ERRATIC_SHARE = 0.25         # ...on more than a quarter of passes = unreliable signal
MAX_DRY_RISE = 0.50          # a rise > 50% of reference area after the reference date...
RISE_RAIN_MM = 10.0          # ...that less than 10 mm of rain can explain = not water level


def _rain_between(precip_by_date: Dict[str, float], start: str, end: str) -> float:
    return sum(p or 0.0 for d, p in precip_by_date.items() if start < d <= end)


def detect_suspect_scenes(
    scene_dates: List[str],
    total_area_by_date: Dict[str, float],
    precip_by_date: Dict[str, float] | None = None,
    jump_threshold: float = SUSPECT_JUMP,
    rain_threshold_mm: float = 5.0,
    neighbours: int = NEIGHBOURS,
) -> List[str]:
    """Scene dates whose total valid water area is an outlier against neighbouring passes.

    Reference = median total of up to `neighbours` non-suspect passes on each side. Suspect if:
      - total is > jump_threshold ABOVE the reference, rain since the previous pass is < 5 mm and
        rain data exists (without rain data, e.g. live post-monsoon, a rise cannot be judged), or
      - total is > jump_threshold BELOW the reference with passes on BOTH sides (a dip that
        recovers; at the end of the series a fall may be real, so it is not judged).
    The worst outlier is removed first and the rest re-checked without it, so one broken pass
    cannot make its good neighbours look like outliers.
    """
    precip_by_date = precip_by_date or {}
    suspect: List[str] = []
    while True:
        worst, worst_change = None, 0.0
        clean = [d for d in scene_dates if d not in suspect]
        for i, d in enumerate(clean):
            before = [total_area_by_date.get(x, 0.0) for x in clean[max(0, i - neighbours):i]]
            after = [total_area_by_date.get(x, 0.0) for x in clean[i + 1:i + 1 + neighbours]]
            ref_vals = [v for v in before + after if v > 0]
            if not ref_vals:
                continue
            ref = median(ref_vals)
            change = (total_area_by_date.get(d, 0.0) - ref) / ref
            if change > jump_threshold:
                if not before or not precip_by_date:
                    continue
                if _rain_between(precip_by_date, clean[i - 1], d) >= rain_threshold_mm:
                    continue
            elif not (change < -jump_threshold and before and after):
                continue
            if abs(change) > abs(worst_change):
                worst, worst_change = d, change
        if worst is None:
            return sorted(suspect)
        suspect.append(worst)


def invalidate_suspect_passes(history: List[dict], suspect_dates: List[str]) -> List[dict]:
    """Readings taken on a suspect pass are not used in any maths."""
    bad = set(suspect_dates)
    return [dict(h, valid=False) if h["date"] in bad else dict(h) for h in history]


def clean_spike_measurements(
    history: List[dict],
    precip_by_date: Dict[str, float] | None = None,
    spike_up_ratio: float = 1.50,
    spike_down_ratio: float = 0.75,
    rain_threshold_mm: float = 5.0,
    dip_ratio: float = 0.50,
    min_dip_ha: float = MIN_DIP_HA,
) -> List[dict]:
    """Mark single-pass spikes and dips invalid.

    Spike: area_i > 1.5 * area_prev and area_next < 0.75 * area_i, unless >= 5 mm rain explains it.
    Dip:   area_i < 0.5 * area_prev and area_next > area_i / 0.5, with both changes >= 0.3 ha
           (water cannot vanish and return within two passes; rain cannot explain a dip).
    Neighbours are the nearest readings that are still valid.
    """
    precip_by_date = precip_by_date or {}
    cleaned = [dict(h) for h in history]
    valid_idx = [i for i, h in enumerate(cleaned) if h.get("valid")]
    if len(valid_idx) < 3:
        return cleaned

    k = 1
    while k < len(valid_idx) - 1:
        prev_h, curr_h, next_h = (cleaned[valid_idx[j]] for j in (k - 1, k, k + 1))
        a_prev, a_curr, a_next = prev_h["areaHa"], curr_h["areaHa"], next_h["areaHa"]

        is_spike = (a_prev > 0.01 and a_curr > spike_up_ratio * a_prev and a_next < spike_down_ratio * a_curr
                    and _rain_between(precip_by_date, prev_h["date"], curr_h["date"]) < rain_threshold_mm)
        is_dip = (a_curr < dip_ratio * a_prev and a_next * dip_ratio > a_curr
                  and a_prev - a_curr >= min_dip_ha and a_next - a_curr >= min_dip_ha)

        if is_spike or is_dip:
            curr_h["valid"] = False
            del valid_idx[k]  # compare the next reading against the same trusted neighbour
            continue
        k += 1
    return cleaned


def assess_pond(history: List[dict], reference_date: str, ref_area_ha: float,
                precip_by_date: Dict[str, float] | None = None,
                existence_history: List[dict] | None = None) -> Tuple[bool, str | None]:
    """(keep, reason). Excludes ponds that were not really there, or whose signal is erratic.

    existence_history: readings BEFORE spike/dip cleaning (that cleaning assumes the pond is real,
    so it must not remove the evidence that it is not). Defaults to history.
    """
    if ref_area_ha <= 0:
        return False, "no water on the reference date"
    ref_day = date.fromisoformat(reference_date)
    valid = [h for h in history if h.get("valid")]

    # 1. Existence: water near the reference area on most clear passes around the reference date
    pre = [h for h in (existence_history if existence_history is not None else history) if h.get("valid")]
    around = [h for h in pre
              if h["date"] != reference_date and abs((date.fromisoformat(h["date"]) - ref_day).days) <= PRESENCE_WINDOW_DAYS]
    if len(around) >= 2:
        present = sum(h["areaHa"] >= PRESENCE_SHARE * ref_area_ha for h in around)
        if present / len(around) < PRESENCE_SHARE:
            return False, (f"water on only {present} of {len(around)} clear passes within "
                           f"{PRESENCE_WINDOW_DAYS} days of the reference date (likely cloud shadow or mis-detection)")

    # 2. Erratic signal: readings jump far from their neighbours too often to be water level
    if len(valid) >= 5:
        jumps = 0
        for prev_h, curr_h, next_h in zip(valid, valid[1:], valid[2:]):
            expected = (prev_h["areaHa"] + next_h["areaHa"]) / 2
            jumps += abs(curr_h["areaHa"] - expected) > ERRATIC_DEVIATION * ref_area_ha
        share = jumps / (len(valid) - 2)
        if share > ERRATIC_SHARE:
            return False, (f"erratic water signal: {jumps} of {len(valid) - 2} readings jump more than "
                           f"{round(100 * ERRATIC_DEVIATION)}% of its size between passes (vegetation, turbidity or shadow)")

    # 3. Unexplained rise: in the dry season a pond cannot regain half its size without rain.
    #    Only judged with rain data (live post-monsoon series have none).
    if precip_by_date:
        after_ref = [h for h in valid if h["date"] > reference_date]
        low = None
        for h in after_ref:
            if low is None or h["areaHa"] < low["areaHa"]:
                low = h
                continue
            rise = h["areaHa"] - low["areaHa"]
            if rise > MAX_DRY_RISE * ref_area_ha and _rain_between(precip_by_date, low["date"], h["date"]) < RISE_RAIN_MM:
                return False, (f"unexplained rise from {low['areaHa']} ha ({low['date']}) to {h['areaHa']} ha "
                               f"({h['date']}) without rain: the signal is not tracking water level")
    return True, None


def apply_quality_rules(
    scenes: List[dict],
    ponds: List[dict],
    precip_by_date: Dict[str, float],
    reference_date: str,
) -> Tuple[List[dict], List[dict], List[dict], dict]:
    """Run every rule in order. Returns (scenes, kept_ponds, excluded_ponds, report).

    scenes: [{"date","id","status"}]; ponds: contract ponds with "history" and "refAreaHa".
    Kept ponds are renumbered P001.. by reference area (largest first), as the contract requires.
    """
    dates = [s["date"] for s in scenes]
    totals = {d: sum(h["areaHa"] for p in ponds for h in p["history"] if h["date"] == d and h.get("valid"))
              for d in dates}
    suspect = detect_suspect_scenes(dates, totals, precip_by_date)
    scenes_out = [dict(s, status="suspect" if s["date"] in suspect else "ok") for s in scenes]

    kept, excluded = [], []
    dips_spikes = 0
    for p in ponds:
        pre = invalidate_suspect_passes(p["history"], suspect)
        hist = clean_spike_measurements(pre, precip_by_date)
        dips_spikes += sum(h["valid"] for h in pre) - sum(h["valid"] for h in hist)
        keep, reason = assess_pond(hist, reference_date, p["refAreaHa"], precip_by_date, existence_history=pre)
        if keep:
            kept.append(dict(p, history=hist))
        else:
            excluded.append({"id": p["id"], "lat": p["lat"], "lon": p["lon"], "refAreaHa": p["refAreaHa"],
                             "place": p.get("place", ""), "reason": reason})

    kept.sort(key=lambda p: p["refAreaHa"], reverse=True)
    for n, p in enumerate(kept, start=1):
        p["id"] = f"P{n:03d}"
    report = {"suspectScenes": suspect, "spikesAndDipsRemoved": dips_spikes,
              "pondsKept": len(kept), "pondsExcluded": len(excluded)}
    return scenes_out, kept, excluded, report
