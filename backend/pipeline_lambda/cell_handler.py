"""Step Functions Map task: process one district cell and save it to S3 (data/{region}/cells/{cell}.json)."""
import json
import os
import time
from datetime import datetime, timezone

import boto3

from pipeline.cell import process_cell

os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")          # Sentinel-2 COGs are public
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")


def season_end(end: str) -> str:
    """'today' (scheduled live runs) -> today's UTC date; anything else is a fixed replay end date."""
    return datetime.now(timezone.utc).date().isoformat() if end == "today" else end


def lambda_handler(event, context):
    started = time.time()
    cell = event["cell"]
    result = process_cell(cell, event["start"], season_end(event["end"]), event["referenceDate"],
                          float(event.get("maxCloud") or 20.0))
    result["seconds"] = round(time.time() - started, 1)
    boto3.client("s3").put_object(Bucket=os.environ["DATA_BUCKET"], Key=f"data/{event['region']}/cells/{cell['id']}.json",
                                  Body=json.dumps(result).encode(), ContentType="application/json")
    summary = {"cell": cell["id"], "ponds": len(result["ponds"]), "passes": len(result["scenes"]), "seconds": result["seconds"]}
    print(json.dumps({"msg": "cell done", **summary}))
    return summary
