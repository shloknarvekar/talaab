"""Recompute job: measurements.json -> published snapshots + DynamoDB, for every region.

Runs every 5 days (EventBridge Scheduler, one new Sentinel-2 pass) and on demand after the
pipeline uploads new measurements (scripts/upload_measurements.py invokes it directly).

Event: {} or {"regions": ["latur-2026"], "today": "YYYY-MM-DD" (optional, for tests/replays)}
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from api import store
from jobs.regions import REGIONS
from jobs.weather import merge_observed, recent_and_forecast
from logic.snapshot import build_snapshot

MIN_HISTORY_DAYS = 20  # first snapshot needs a few passes to fit a trend
IST = timezone(timedelta(hours=5, minutes=30))


def snapshot_dates(meas: dict, today: date | None) -> list[str]:
    scenes = [s["date"] for s in meas["scenes"]]
    if not scenes:
        return [today.isoformat()] if today else []
    first = date.fromisoformat(scenes[0])
    dates = {d for d in scenes if date.fromisoformat(d) >= first + timedelta(days=MIN_HISTORY_DAYS)}
    if today:
        dates.add(today.isoformat())
    return sorted(dates)


def write_ponds_table(region: str, snap: dict) -> int:
    """Upsert each pond's latest state (pk regionId, sk pondId). Skipped when no table is configured."""
    table_name = os.environ.get("PONDS_TABLE")
    if not table_name:
        return 0
    import boto3

    table = boto3.resource("dynamodb").Table(table_name)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with table.batch_writer() as batch:
        for p in snap["ponds"]:
            item = json.loads(json.dumps(p), parse_float=Decimal)
            item.update(regionId=region, pondId=p["id"], asOf=snap["asOf"], updatedAt=now)
            item.pop("id", None)
            batch.put_item(Item=item)
    return len(snap["ponds"])


def recompute_region(region: str, today: date, fetch_weather: Callable = recent_and_forecast,
                     write_table: Callable = write_ponds_table) -> dict:
    cfg = REGIONS[region]
    meas = store.read_json(f"{region}/measurements.json", fresh=True)
    if meas is None:
        return {"region": region, "skipped": "no measurements.json uploaded yet"}

    live = cfg["mode"] == "live"
    forecast: list[dict] = []
    if live:
        lat, lon = cfg["centre"]
        observed, forecast = fetch_weather(lat, lon, today)
        meas = {**meas, "et0": merge_observed(meas.get("et0", []), observed)}

    dates = snapshot_dates(meas, today if live else None)
    latest = None
    for d in dates:
        # the forecast is only knowable on the day it was fetched, so only today's snapshot uses it
        src = {**meas, "et0Forecast": forecast} if (live and d == today.isoformat()) else {**meas, "et0Forecast": []}
        snap = build_snapshot(src, d)
        snap["region"] = {**snap["region"], "id": region, "name": cfg["name"]}
        if live:
            snap["live"] = True
        store.write_json(f"{region}/asof/{d}.json", snap)
        latest = snap

    published = sorted(k.rsplit("/", 1)[-1][:-5] for k in store.list_keys(f"{region}/asof/") if k.endswith(".json"))
    store.write_json(f"{region}/index.json", {"asOf": published, "mode": cfg["mode"], "name": cfg["name"]})

    counts: dict[str, int] = {}
    for p in latest["ponds"] if latest else []:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    rows = write_table(region, latest) if latest else 0
    return {
        "region": region,
        "mode": cfg["mode"],
        "snapshots": len(dates),
        "latestAsOf": latest["asOf"] if latest else None,
        "ponds": len(latest["ponds"]) if latest else 0,
        "status": counts,
        "flagged": [p["id"] for p in latest["ponds"] if p["flag"]] if latest else [],
        "sunShareMm": latest["sunShareMm"] if latest else None,
        "forecastDays": len(forecast),
        "dynamoRows": rows,
    }


def lambda_handler(event, context):
    event = event or {}
    today = date.fromisoformat(event["today"]) if event.get("today") else datetime.now(IST).date()
    regions = event.get("regions") or list(REGIONS)
    started = time.time()
    results = []
    for region in regions:
        if region not in REGIONS:
            results.append({"region": region, "error": "unknown region"})
            continue
        try:
            results.append(recompute_region(region, today))
        except Exception as e:  # one bad region must not stop the others
            results.append({"region": region, "error": f"{type(e).__name__}: {e}"[:300]})
        print(json.dumps({"msg": "recompute", **results[-1]}))
    summary = {"today": today.isoformat(), "seconds": round(time.time() - started, 1), "results": results}
    print(json.dumps({"msg": "recompute done", "seconds": summary["seconds"]}))
    return summary
