"""Regions Talaab tracks.

replay: past season with complete data (honest backtest; heat expectation from climatology).
live:   the current season; the recompute job adds observed + forecast weather from Open-Meteo
        and publishes a snapshot for today on every run.
"""
LATUR_BBOX = [76.47, 18.33, 76.62, 18.48]
LATUR_CENTRE = (18.405, 76.545)  # lat, lon for weather
LATUR_DISTRICT_BBOX = [76.2024, 17.8709, 77.2953, 18.8389]  # OSM district boundary (pipeline/boundaries)
LATUR_DISTRICT_CENTRE = (18.355, 76.749)

REGIONS = {
    "latur-2024": {"name": "Latur (2024 replay)", "mode": "replay", "bbox": LATUR_BBOX, "centre": LATUR_CENTRE},
    "latur-2024-synthetic": {"name": "Latur (2024 replay, SYNTHETIC data)", "mode": "replay", "bbox": LATUR_BBOX, "centre": LATUR_CENTRE},
    # alerts off: the live district covers this box, so its ponds are emailed once, by the district
    "latur-2026": {"name": "Latur (live, 2026)", "mode": "live", "bbox": LATUR_BBOX, "centre": LATUR_CENTRE, "alerts": False},
    # Whole district (7,157 km2), processed on AWS by the district state machine (scripts/run_district.py)
    "latur-district-2024": {"name": "Latur district (2024 replay)", "mode": "replay",
                            "bbox": LATUR_DISTRICT_BBOX, "centre": LATUR_DISTRICT_CENTRE},
    # Whole district, live: the district state machine re-measures it every 5 days (EventBridge Scheduler)
    "latur-district-2026": {"name": "Latur district (live, 2026)", "mode": "live",
                            "bbox": LATUR_DISTRICT_BBOX, "centre": LATUR_DISTRICT_CENTRE},
}
