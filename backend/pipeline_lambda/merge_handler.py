"""Step Functions final task: merge cells -> district measurements.json -> recompute.

Keeps ponds inside the district boundary, applies the pipeline's quality rules district-wide,
adds observed weather and 2019-2023 climatology for the district centre, then starts the normal
recompute job (snapshots, DynamoDB, alerts, timeline).
"""
import json
import os
import time
from datetime import date, timedelta

import boto3

os.environ.setdefault("TALAAB_CACHE_DIR", "/tmp/talaab-cache")  # Lambda code folder is read-only

from pipeline.cleanup import apply_quality_rules
from pipeline.district import load_boundary, merge_cells
from pipeline.evaporation import fetch_climatology_2019_2023, fetch_daily_weather


def lambda_handler(event, context):
    started = time.time()
    region, bucket = event["region"], os.environ["DATA_BUCKET"]
    s3 = boto3.client("s3")
    boundary = load_boundary(event["boundary"])
    keys = [o["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"data/{region}/cells/")
            for o in page.get("Contents", [])]
    cells = [json.loads(s3.get_object(Bucket=bucket, Key=k)["Body"].read()) for k in keys]

    scenes, ponds = merge_cells(cells, boundary["geometry"])

    w, s, e, n = boundary["bbox"]
    lat, lon = (s + n) / 2, (w + e) / 2
    first, last = date.fromisoformat(scenes[0]["date"]), date.fromisoformat(scenes[-1]["date"])
    et0 = fetch_daily_weather((first - timedelta(days=45)).isoformat(), last.isoformat(), lat=lat, lon=lon)
    clim = fetch_climatology_2019_2023(lat=lat, lon=lon)
    precip = {x["date"]: x.get("precip") or 0.0 for x in et0}

    scenes, kept, excluded, quality = apply_quality_rules(scenes, ponds, precip, event["referenceDate"])
    doc = {"region": {"id": region, "name": event["name"], "bbox": boundary["bbox"]}, "generatedAt": date.today().isoformat(),
           "referenceDate": event["referenceDate"], "scenes": scenes, "et0": et0, "et0Climatology": clim,
           "ponds": kept, "excludedPonds": excluded, "quality": quality}
    s3.put_object(Bucket=bucket, Key=f"data/{region}/measurements.json", Body=json.dumps(doc).encode(), ContentType="application/json")

    run = {"cells": len(cells), "pondsDetected": len(ponds), "pondsKept": len(kept), "pondsExcluded": len(excluded),
           "passes": len(scenes), "cellSeconds": sum(c.get("seconds", 0) for c in cells),
           "slowestCellSeconds": max((c.get("seconds", 0) for c in cells), default=0), "mergeSeconds": round(time.time() - started, 1)}
    s3.put_object(Bucket=bucket, Key=f"data/{region}/run.json", Body=json.dumps(run).encode(), ContentType="application/json")
    boto3.client("lambda").invoke(FunctionName=os.environ["RECOMPUTE_FUNCTION"], InvocationType="Event",
                                  Payload=json.dumps({"regions": [region]}).encode())
    print(json.dumps({"msg": "district merged", "region": region, **run}))
    return run
