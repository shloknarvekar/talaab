"""Generate a SYNTHETIC measurements.json for Latur Jan-Jun 2024 (clearly labelled, not real data).

Lets the backend, API, web map and demo run end to end before the real satellite pipeline lands.
Ponds shrink with the sun (rate scales with ET0); two ponds get extra "pumping" from a given
date so the faster-than-sun flag has something to find; one pumped pond is too small to flag.

    python backend/scripts/synth_measurements.py [out.json]
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

BBOX = [76.47, 18.33, 76.62, 18.48]
START, END = date(2024, 1, 16), date(2024, 6, 14)
VILLAGES = "ABCDEFGHIJKLMN"


def et0_curve(d: date) -> float:
    """Rough Marathwada dry-season ET0: ~4 mm/day in Jan rising to ~8 in May, easing with June rain."""
    doy = d.timetuple().tm_yday
    base = 3.9 + 4.3 * min(1.0, max(0.0, (doy - 15) / 135))
    if d >= date(d.year, 6, 8):
        base -= 2.5
    return round(base, 2)


def generate(seed: int = 42) -> dict:
    rng = random.Random(seed)

    days = [START - timedelta(days=60) + timedelta(days=i) for i in range((END - START).days + 61)]
    et0 = []
    for d in days:
        precip = 0.0
        if d >= date(2024, 6, 8):
            precip = round(rng.uniform(0, 14), 1)
        elif rng.random() < 0.03:
            precip = round(rng.uniform(0.5, 6), 1)
        et0.append({"date": d.isoformat(), "et0": round(et0_curve(d) + rng.uniform(-0.4, 0.4), 2), "precip": precip})
    clim = {}
    for i in range(366):
        d = date(2020, 1, 1) + timedelta(days=i)
        clim[d.strftime("%m-%d")] = round(et0_curve(date(2024, d.month, d.day)) - 0.15, 2)

    scene_dates = [START + timedelta(days=5 * i) for i in range((END - START).days // 5 + 1)]
    suspect = {date(2024, 3, 1)}
    scenes = [
        {"date": d.isoformat(), "id": f"{'S2B' if i % 2 == 0 else 'S2A'}_43QFA_{d:%Y%m%d}_0_L2A",
         "status": "suspect" if d in suspect else "ok"}
        for i, d in enumerate(scene_dates)
    ]

    # (refAreaHa, base relative loss per day at ET0 = 5 mm, pumping extra ha/day, pumping start)
    specs = [(92.0, 0.0028, 0, None), (61.0, 0.0034, 0, None), (44.0, 0.0040, 0.38, date(2024, 2, 20)),
             (38.5, 0.0038, 0, None), (27.0, 0.0045, 0, None), (21.0, 0.0050, 0, None),
             (16.5, 0.0042, 0.21, date(2024, 3, 25)), (12.0, 0.0055, 0, None), (8.4, 0.0060, 0, None),
             (6.1, 0.0048, 0, None), (4.3, 0.0070, 0, None), (3.0, 0.0065, 0, None),
             (1.6, 0.0060, 0.03, date(2024, 2, 1)), (1.2, 0.0000, 0, None)]  # last: spring-fed, stable
    et0_by_day = {x["date"]: x["et0"] for x in et0}

    ponds = []
    for n, (ref, r, pump, pump_from) in enumerate(specs):
        area, hist, d = ref, [], START
        for sd in scene_dates:
            while d < sd:
                loss = ref * r * et0_by_day[d.isoformat()] / 5.0
                if pump_from and d >= pump_from:
                    loss += pump
                area = max(0.0, area - loss)
                d += timedelta(days=1)
            measured = area * (1 + rng.uniform(-0.02, 0.02)) if area > 0 else 0.0
            valid = rng.random() > 0.08
            if sd in suspect:
                measured, valid = measured * 1.45, False
            if sd == START:
                measured, valid = ref, True
            hist.append({"date": sd.isoformat(), "areaHa": round(measured, 2), "valid": valid})
        lon = round(BBOX[0] + 0.012 + rng.random() * (BBOX[2] - BBOX[0] - 0.024), 4)
        lat = round(BBOX[1] + 0.012 + rng.random() * (BBOX[3] - BBOX[1] - 0.024), 4)
        ponds.append({"id": f"P{n + 1:03d}", "lat": lat, "lon": lon,
                      "place": f"near Village {VILLAGES[n]} (synthetic)", "refAreaHa": ref, "history": hist})

    return {
        "synthetic": True,
        "region": {"id": "latur-2024-synthetic", "name": "Latur (2024 replay, SYNTHETIC data)", "bbox": BBOX},
        "generatedAt": "synthetic",
        "referenceDate": START.isoformat(),
        "scenes": scenes,
        "et0": et0,
        "et0Climatology": clim,
        "ponds": ponds,
    }


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/latur-2024-synthetic/measurements.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(generate(), indent=1), encoding="utf-8")
    print(f"wrote {out}")
