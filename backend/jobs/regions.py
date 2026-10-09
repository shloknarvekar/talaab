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

# The rest of Marathwada (all 8 drought districts of the Chhatrapati Sambhajinagar division), live, run on
# AWS by the same state machine one district after another. Boundaries: pipeline/boundaries/<slug>-district.json
# (scripts/fetch_districts.py). (slug, name, bbox [W, S, E, N], centre (lat, lon) for weather)
MARATHWADA = [
    ("beed", "Beed", [74.8081, 18.5418, 76.7339, 19.4419], (18.992, 75.771)),
    ("dharashiv", "Dharashiv", [75.2854, 17.6416, 76.7908, 18.6982], (18.170, 76.038)),
    ("nanded", "Nanded", [76.9308, 18.2634, 78.3652, 19.9250], (19.094, 77.648)),
    ("parbhani", "Parbhani", [76.2072, 18.7504, 77.1194, 19.8306], (19.291, 76.663)),
    ("hingoli", "Hingoli", [76.5119, 19.0672, 77.4893, 20.0179], (19.543, 77.001)),
    ("jalna", "Jalna", [75.5854, 19.2767, 76.5346, 20.5610], (19.919, 76.060)),
    ("sambhajinagar", "Chhatrapati Sambhajinagar", [74.5889, 19.3780, 76.0427, 20.6685], (20.023, 75.316)),
]
for _slug, _name, _bbox, _centre in MARATHWADA:
    REGIONS[f"{_slug}-district-2026"] = {"name": f"{_name} district (live, 2026)", "mode": "live",
                                         "bbox": _bbox, "centre": _centre}
