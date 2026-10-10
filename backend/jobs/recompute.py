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
from jobs.alerts import alert_state, alert_timeline, format_alert, format_digest, new_alerts
from jobs.places import name_ponds, places_for_region
from jobs.talukas import tag_ponds, talukas_for_region
from jobs.regions import DISTRICT_MR, DIVISIONS, REGIONS, district_name, division_members
from jobs.weather import merge_observed, recent_and_forecast
from logic.division import summarise_division
from logic.snapshot import build_snapshot

MIN_HISTORY_DAYS = 20  # first snapshot needs a few passes to fit a trend
SITE_URL = os.environ.get("SITE_URL", "https://main.duvnkrxj02sz1.amplifyapp.com")
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


def sns_publish(subject: str, body: str) -> bool:
    """Publish to the alert topic. Returns False when no topic is configured (local runs, tests)."""
    topic = os.environ.get("ALERT_TOPIC_ARN")
    if not topic:
        return False
    import boto3

    boto3.client("sns").publish(TopicArn=topic, Subject=subject, Message=body)
    return True


def send_alerts(region: str, cfg: dict, snap: dict, publish: Callable[[str, str], bool] = sns_publish) -> int:
    """Email ponds that newly turned critical / dry / faster-than-sun since the last run (live only)."""
    prev = store.read_json(f"{region}/alerts/state.json", fresh=True) or {}
    alerts = new_alerts(prev, snap)
    sent = 0
    if alerts:
        subject, body = format_alert(cfg["name"], snap["asOf"], alerts, SITE_URL)
        delivered = publish(subject, body)
        store.write_json(f"{region}/alerts/{snap['asOf']}.json",
                         {"asOf": snap["asOf"], "subject": subject, "body": body, "delivered": delivered, "alerts": alerts})
        print(json.dumps({"msg": "alerts", "region": region, "count": len(alerts), "delivered": delivered, "subject": subject}))
        sent = len(alerts) if delivered else 0
    store.write_json(f"{region}/alerts/state.json", alert_state(snap, prev, alerts if sent else []))
    return sent


def queue_alerts(region: str, cfg: dict, snap: dict) -> int:
    """Division members don't email on their own: new alerts wait in the division outbox for ONE digest.

    Marked as alerted now (so the next recompute doesn't queue them again); one outbox file per district so
    district recomputes running at the same time can't overwrite each other's alerts."""
    prev = store.read_json(f"{region}/alerts/state.json", fresh=True) or {}
    alerts = new_alerts(prev, snap)
    if alerts:
        key = f"{cfg['division']}/alerts/outbox/{region}.json"
        box = store.read_json(key, fresh=True) or {"alerts": []}
        box["alerts"] += [dict(a, region=region, district=district_name(region), asOf=snap["asOf"]) for a in alerts]
        store.write_json(key, box)
    store.write_json(f"{region}/alerts/state.json", alert_state(snap, prev, alerts))
    return len(alerts)


def write_division(division_id: str) -> dict | None:
    """Division summary from each member's latest published snapshot -> {division}/division.json (+ a dated copy)."""
    members = []
    for region in division_members(division_id):
        index = store.read_json(f"{region}/index.json", fresh=True) or {}
        snap = store.read_json(f"{region}/asof/{index['asOf'][-1]}.json", fresh=True) if index.get("asOf") else None
        if snap:
            members.append((region, district_name(region), snap))
    if not members:
        return None
    cfg = DIVISIONS[division_id]
    doc = summarise_division({"id": division_id, "name": cfg["name"], "nameMr": cfg.get("nameMr"), "live": True}, members, DISTRICT_MR)
    store.write_json(f"{division_id}/division.json", doc)
    store.write_json(f"{division_id}/division/{doc['asOf']}.json", doc)
    return doc


def send_digest(division_id: str, publish: Callable[[str, str], bool] | None = None) -> int:
    """ONE email with every queued alert of the division; then log it per district and empty the outbox.

    If publishing raises, the outbox is kept and the alerts go out with the next digest."""
    publish = publish or sns_publish
    keys = [k for k in store.list_keys(f"{division_id}/alerts/outbox/") if k.endswith(".json")]
    boxes = {k: (store.read_json(k, fresh=True) or {}).get("alerts", []) for k in keys}
    alerts = [a for box in boxes.values() for a in box]
    if not alerts:
        return 0
    doc = store.read_json(f"{division_id}/division.json", fresh=True) or write_division(division_id)
    subject, body = format_digest(DIVISIONS[division_id]["name"], doc["asOf"], doc, alerts, SITE_URL)
    delivered = publish(subject, body)
    stamp = datetime.now(IST).strftime("%Y-%m-%d-%H%M%S")
    store.write_json(f"{division_id}/alerts/{stamp}.json", {"asOf": doc["asOf"], "subject": subject, "body": body,
                                                            "delivered": delivered, "alerts": alerts})
    for region in sorted({a["region"] for a in alerts}):  # GET /alerts per district = what was actually sent
        mine = [a for a in alerts if a["region"] == region]
        store.write_json(f"{region}/alerts/{stamp}.json", {"asOf": max(a["asOf"] for a in mine), "subject": subject,
                                                           "delivered": delivered, "alerts": mine, "digest": division_id})
        write_alert_timeline(region, REGIONS[region], [], live=True)
    for k in keys:
        store.write_json(k, {"alerts": []})
    print(json.dumps({"msg": "alerts", "region": division_id, "count": len(alerts), "delivered": delivered, "subject": subject}))
    return len(alerts) if delivered else 0


def write_alert_timeline(region: str, cfg: dict, snaps: list[dict], live: bool) -> None:
    """GET /alerts: replay = alerts Talaab would have sent pass by pass; live = alerts actually sent."""
    if live:
        logs = [store.read_json(k, fresh=True) for k in store.list_keys(f"{region}/alerts/")
                if k.rsplit("/", 1)[-1][:4].isdigit()]
        events = [{"asOf": x["asOf"], "subject": x["subject"], "alerts": x["alerts"], "delivered": x.get("delivered")}
                  for x in sorted((x for x in logs if x), key=lambda x: x["asOf"])]
    else:
        events = alert_timeline(snaps, cfg["name"], SITE_URL)
    store.write_json(f"{region}/alerts/timeline.json",
                     {"region": region, "name": cfg["name"], "simulated": not live, "events": events})


def recompute_region(region: str, today: date, fetch_weather: Callable = recent_and_forecast,
                     write_table: Callable = write_ponds_table, publish: Callable = sns_publish) -> dict:
    cfg = REGIONS[region]
    meas = store.read_json(f"{region}/measurements.json", fresh=True)
    if meas is None:
        return {"region": region, "skipped": "no measurements.json uploaded yet"}

    meas = {**meas, "ponds": [dict(p) for p in meas["ponds"]]}
    named = name_ponds(meas["ponds"], places_for_region(region))
    in_taluka = tag_ponds(meas["ponds"], talukas_for_region(region))

    live = cfg["mode"] == "live"
    forecast: list[dict] = []
    if live:
        lat, lon = cfg["centre"]
        observed, forecast = fetch_weather(lat, lon, today)
        meas = {**meas, "et0": merge_observed(meas.get("et0", []), observed)}

    dates = snapshot_dates(meas, today if live else None)
    latest = None
    snaps: list[dict] = []
    for d in dates:
        # the forecast is only knowable on the day it was fetched, so only today's snapshot uses it
        src = {**meas, "et0Forecast": forecast} if (live and d == today.isoformat()) else {**meas, "et0Forecast": []}
        snap = build_snapshot(src, d)
        snap["region"] = {**snap["region"], "id": region, "name": cfg["name"]}
        if live:
            snap["live"] = True
        store.write_json(f"{region}/asof/{d}.json", snap)
        snaps.append(snap)
        latest = snap

    published = sorted(k.rsplit("/", 1)[-1][:-5] for k in store.list_keys(f"{region}/asof/") if k.endswith(".json"))
    store.write_json(f"{region}/index.json", {"asOf": published, "mode": cfg["mode"], "name": cfg["name"]})

    counts: dict[str, int] = {}
    for p in latest["ponds"] if latest else []:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    rows = write_table(region, latest) if latest else 0
    alerts_sent = alerts_queued = 0
    if live and latest and cfg.get("alerts", True):
        if cfg.get("division"):  # one digest per division run instead of an email per district
            alerts_queued = queue_alerts(region, cfg, latest)
        else:
            alerts_sent = send_alerts(region, cfg, latest, publish)
    write_alert_timeline(region, cfg, snaps, live)
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
        "pondsNamed": named,
        "pondsWithTaluka": in_taluka,
        "alertsSent": alerts_sent,
        "alertsQueued": alerts_queued,
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

    # Divisions: refresh the summary whenever a member was recomputed; send the digest only when asked
    # (end of the Marathwada workflow, and the scheduled full run). A single district's recompute, e.g. after
    # its merge, only queues, so a Marathwada run sends one email, not eight.
    digest = event.get("digest", not event.get("regions"))
    divisions = []
    for division_id in sorted({REGIONS[r].get("division") for r in regions if r in REGIONS} - {None}):
        try:
            doc = write_division(division_id)
            sent = send_digest(division_id) if digest else 0
            divisions.append({"division": division_id, "asOf": doc and doc["asOf"], "ponds": doc and doc["totals"]["ponds"],
                              "digest": digest, "alertsSent": sent})
        except Exception as e:  # noqa: BLE001 - the regions above are already published
            divisions.append({"division": division_id, "error": f"{type(e).__name__}: {e}"[:300]})
        print(json.dumps({"msg": "division", **divisions[-1]}))
    summary = {"today": today.isoformat(), "seconds": round(time.time() - started, 1), "results": results, "divisions": divisions}
    print(json.dumps({"msg": "recompute done", "seconds": summary["seconds"]}))
    return summary
