"""Cleanup and quality assurance module.

Implements scene-level suspect detection (region-wide area jumps without rain)
and pond-level single-point spike dropping.

Data credits: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search).
"""

from __future__ import annotations

from typing import Dict, List, Tuple


def detect_suspect_scenes(
    scene_dates: List[str],
    total_area_by_date: Dict[str, float],
    precip_by_date: Dict[str, float] | None = None,
    jump_threshold: float = 0.40,
    rain_threshold_mm: float = 5.0,
) -> List[str]:
    """Identify scene dates that should be marked 'suspect'.

    A scene is suspect if total region valid water area jumps by >40% compared to
    the previous clear pass, and cumulative rainfall between the passes is < 5 mm.
    """
    if precip_by_date is None:
        precip_by_date = {}

    suspect_dates: List[str] = []

    for i in range(1, len(scene_dates)):
        prev_date = scene_dates[i - 1]
        curr_date = scene_dates[i]

        prev_area = total_area_by_date.get(prev_date, 0.0)
        curr_area = total_area_by_date.get(curr_date, 0.0)

        if prev_area <= 0:
            continue

        area_change_ratio = (curr_area - prev_area) / prev_area

        if area_change_ratio > jump_threshold:
            # Calculate total rain between prev_date and curr_date
            # (simple lookup sum over dates if available)
            rain_sum = 0.0
            for d, precip in precip_by_date.items():
                if prev_date < d <= curr_date:
                    rain_sum += precip

            if rain_sum < rain_threshold_mm:
                suspect_dates.append(curr_date)

    return suspect_dates


def clean_spike_measurements(
    history: List[dict],
    precip_by_date: Dict[str, float] | None = None,
    spike_up_ratio: float = 1.50,
    spike_down_ratio: float = 0.75,
    rain_threshold_mm: float = 5.0,
) -> List[dict]:
    """Clean single-point area spikes in a pond's history.

    Sets valid=False on pass i if area_i > 1.5 * area_{i-1} AND area_{i+1} < 0.75 * area_i,
    unless explained by precipitation >= 5mm between pass i-1 and pass i.
    """
    if precip_by_date is None:
        precip_by_date = {}

    # Copy history so we do not mutate in-place unexpectedly
    cleaned_history = [dict(h) for h in history]

    # Find valid measurement indices
    valid_indices = [idx for idx, h in enumerate(cleaned_history) if h.get("valid")]

    if len(valid_indices) < 3:
        return cleaned_history

    for k in range(1, len(valid_indices) - 1):
        idx_prev = valid_indices[k - 1]
        idx_curr = valid_indices[k]
        idx_next = valid_indices[k + 1]

        prev_h = cleaned_history[idx_prev]
        curr_h = cleaned_history[idx_curr]
        next_h = cleaned_history[idx_next]

        area_prev = prev_h["areaHa"]
        area_curr = curr_h["areaHa"]
        area_next = next_h["areaHa"]

        if area_prev <= 0.01:
            continue

        # Check for single-point spike (up > 50%, then down < 75%)
        is_spike_up = area_curr > (spike_up_ratio * area_prev)
        is_spike_down = area_next < (spike_down_ratio * area_curr)

        if is_spike_up and is_spike_down:
            # Check rain between prev date and curr date
            prev_date = prev_h["date"]
            curr_date = curr_h["date"]
            rain_sum = sum(
                p for d, p in precip_by_date.items() if prev_date < d <= curr_date
            )

            if rain_sum < rain_threshold_mm:
                curr_h["valid"] = False

    return cleaned_history
