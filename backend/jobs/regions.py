"""Regions Talaab tracks.

replay: past season with complete data (honest backtest; heat expectation from climatology).
live:   the current season; the recompute job adds observed + forecast weather from Open-Meteo
        and publishes a snapshot for today on every run.
"""
LATUR_BBOX = [76.47, 18.33, 76.62, 18.48]
LATUR_CENTRE = (18.405, 76.545)  # lat, lon for weather

REGIONS = {
    "latur-2024": {"name": "Latur (2024 replay)", "mode": "replay", "bbox": LATUR_BBOX, "centre": LATUR_CENTRE},
    "latur-2024-synthetic": {"name": "Latur (2024 replay, SYNTHETIC data)", "mode": "replay", "bbox": LATUR_BBOX, "centre": LATUR_CENTRE},
    "latur-2026": {"name": "Latur (live, 2026)", "mode": "live", "bbox": LATUR_BBOX, "centre": LATUR_CENTRE},
}
