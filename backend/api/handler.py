"""Talaab HTTP API (API Gateway HTTP API, payload format 2.0).

GET  /regions                                   -> regions with published dates (for the map)
GET  /ponds?region=latur-2024&asOf=YYYY-MM-DD   -> ponds.json document
GET  /ponds/{id}?region=...&asOf=...            -> one pond
POST /plan {region, asOf, language: en|mr}      -> {markdown, pondIds, source, status}
GET  /backtest?region=latur-2024                -> how well past predictions matched reality
GET  /alerts?region=latur-2024                  -> alert timeline (replay: simulated; live: sent)
GET  /division?division=marathwada-2026&asOf=... -> summary of every district of the division
GET  /division/outlines?division=...            -> district outlines (GeoJSON) for the division map
GET  /imagery/{region}/...                      -> district satellite imagery (index, outlines, thumbnails)

asOf picks the latest published snapshot on or before that date, so a replay never
shows data from after the date the user chose.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from api import store
from api.plans import get_plan
from jobs.regions import DIVISIONS, REGIONS, division_members
from logic.plan import build_division_plan

DEFAULT_REGION = os.environ.get("DEFAULT_REGION", "latur-2024")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REGION_RE = re.compile(r"^[a-z0-9-]{1,40}$")
POND_RE = re.compile(r"^P\d{3,4}$")
DEFAULT_DIVISION = "marathwada-2026"
OUTLINES_DIR = Path(__file__).resolve().parents[1] / "jobs" / "places"  # scripts/build_division_outlines.py


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _region_and_date(region: str | None, as_of: str | None) -> tuple[str, str | None]:
    region = region or DEFAULT_REGION
    if not REGION_RE.match(region):
        raise HttpError(400, "region must be a slug like latur-2024")
    if as_of is not None and not DATE_RE.match(as_of):
        raise HttpError(400, "asOf must be YYYY-MM-DD")
    return region, as_of


def _load(region: str, as_of: str | None) -> dict:
    doc = store.get_ponds_doc(region, as_of)
    if doc is None:
        raise HttpError(404, f"no data for region {region!r} on or before {as_of or 'latest'}")
    return doc


def get_regions() -> dict:
    """Regions that have published snapshots, with the exact dates the map slider can use, and the divisions
    that have a summary (members = their district regions, dates = the dated summaries)."""
    out = []
    for region_id, cfg in REGIONS.items():
        index = store.read_json(f"{region_id}/index.json")
        dates = sorted(index.get("asOf", [])) if index else []
        if not dates:
            continue
        out.append({"id": region_id, "name": cfg["name"], "mode": cfg["mode"], "bbox": cfg["bbox"],
                    "synthetic": region_id.endswith("-synthetic"),
                    "first": dates[0], "last": dates[-1], "dates": dates})
    divisions = []
    for division_id, cfg in DIVISIONS.items():
        dates = _division_dates(division_id)
        if dates:
            divisions.append({"id": division_id, "name": cfg["name"], "nameMr": cfg.get("nameMr"),
                              "members": division_members(division_id), "first": dates[0], "last": dates[-1], "dates": dates})
    return {"regions": out, "divisions": divisions}


def _division_dates(division: str) -> list[str]:
    return sorted(k.rsplit("/", 1)[-1][:-5] for k in store.list_keys(f"{division}/division/") if k.endswith(".json"))


def _division_id(query: dict) -> str:
    division = query.get("division") or DEFAULT_DIVISION
    if not REGION_RE.match(division) or division not in DIVISIONS:
        raise HttpError(404, f"unknown division {division!r}; known: {', '.join(DIVISIONS)}")
    return division


def get_ponds(query: dict) -> dict:
    region, as_of = _region_and_date(query.get("region"), query.get("asOf"))
    return _load(region, as_of)


def get_pond(pond_id: str, query: dict) -> dict:
    if not POND_RE.match(pond_id or ""):
        raise HttpError(400, "pond id must look like P001")
    region, as_of = _region_and_date(query.get("region"), query.get("asOf"))
    if as_of is None:  # latest state: one DynamoDB item (recompute keeps it current); dated views use S3 snapshots
        latest = store.get_latest_pond(region, pond_id)
        if latest:
            return {**latest, "region": region}
    doc = _load(region, as_of)
    for pond in doc["ponds"]:
        if pond["id"] == pond_id:
            return {**pond, "asOf": doc["asOf"], "region": doc["region"]["id"]}
    raise HttpError(404, f"pond {pond_id} not found in {region} as of {doc['asOf']}")


def get_division(query: dict) -> dict:
    """The division summary (written by recompute): latest, or the latest on or before ?asOf (never the future)."""
    division = _division_id(query)
    _, as_of = _region_and_date(division, query.get("asOf"))
    if as_of is None:
        doc = store.read_json(f"{division}/division.json")
    else:
        earlier = [d for d in _division_dates(division) if d <= as_of]
        doc = store.read_json(f"{division}/division/{earlier[-1]}.json") if earlier else None
    if doc is None:
        raise HttpError(404, f"no division summary for {division!r}" + (f" on or before {as_of}" if as_of else " yet"))
    return doc


@lru_cache(maxsize=4)
def _outlines(division: str) -> dict | None:
    path = OUTLINES_DIR / f"{division}-districts.geojson"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def get_division_outlines(query: dict) -> dict:
    """District outlines for the division map (static, bundled; join to GET /division rows on properties.region)."""
    doc = _outlines(_division_id(query))
    if doc is None:
        raise HttpError(404, "no outlines for this division yet")
    return doc


def post_plan(body: dict) -> dict:
    region, as_of = _region_and_date(body.get("region"), body.get("asOf"))
    language = body.get("language", "en")
    if language not in ("en", "mr"):
        raise HttpError(400, "language must be 'en' or 'mr'")
    if region in DIVISIONS:  # the Divisional Commissioner's overview, from the division summary
        div = get_division({"division": region, "asOf": as_of})
        return get_plan(div, language, template=build_division_plan(div, language), region=region)
    doc = _load(region, as_of)
    return get_plan(doc, language)


GZIP_MIN_BYTES = 1024
# District imagery is made on AWS (pipeline merge -> s3://<bucket>/data/<region>/imagery/...). Only these files can
# be asked for; a thumbnail is answered with a short-lived signed S3 link so the image bytes never pass the Lambda.
IMAGERY_RE = re.compile(r"^(?P<region>[a-z0-9]+(?:-[a-z0-9]+)*)/(?P<file>index\.json|outlines\.geojson|P\d{3,5}/\d{4}-\d{2}-\d{2}\.jpg)$")
THUMB_LINK_SECONDS = 3600


def get_imagery(path: str | None) -> dict:
    m = IMAGERY_RE.match(path or "")
    if not m:
        raise HttpError(404, "no such imagery file")
    region, name = m["region"], m["file"]
    if name.endswith(".jpg"):
        bucket = os.environ.get("DATA_BUCKET")
        if not bucket:
            raise HttpError(404, "thumbnails are served from S3 only")
        url = store._s3_client().generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": f"data/{region}/imagery/{name}"}, ExpiresIn=THUMB_LINK_SECONDS)
        return {"statusCode": 302, "headers": {"location": url, "cache-control": f"private, max-age={THUMB_LINK_SECONDS - 300}"},
                "body": ""}
    doc = store.read_json(f"{region}/imagery/{name}")
    if doc is None:
        raise HttpError(404, f"no imagery for region {region!r} yet")
    return _response(200, doc)


def _compress(response: dict, event: dict) -> dict:
    """gzip the JSON when the client accepts it (every browser does): a district snapshot shrinks ~10x.

    API Gateway HTTP APIs pass a base64 body with content-encoding through unchanged. CloudFront would do
    this at the edge, but new AWS accounts can't create distributions until AWS verifies them."""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = response.get("body") or ""
    if "gzip" not in headers.get("accept-encoding", "") or len(body) < GZIP_MIN_BYTES:
        return response
    packed = gzip.compress(body.encode("utf-8"), compresslevel=6)
    return {**response, "body": base64.b64encode(packed).decode("ascii"), "isBase64Encoded": True,
            "headers": {**response["headers"], "content-encoding": "gzip", "vary": "accept-encoding"}}


def lambda_handler(event, context):
    return _compress(_route(event), event)


def _route(event):
    route = event.get("routeKey", "")
    query = event.get("queryStringParameters") or {}
    print(json.dumps({"route": route, "query": query}))
    try:
        if route == "GET /regions":
            return _response(200, get_regions())
        if route == "GET /ponds":
            return _response(200, get_ponds(query))
        if route == "GET /ponds/{id}":
            return _response(200, get_pond((event.get("pathParameters") or {}).get("id"), query))
        if route == "GET /division":
            return _response(200, get_division(query))
        if route == "GET /division/outlines":
            r = _response(200, get_division_outlines(query))
            r["headers"]["cache-control"] = "public, max-age=86400"  # changes only when the boundaries are rebuilt
            return r
        if route == "GET /imagery/{proxy+}":
            return get_imagery((event.get("pathParameters") or {}).get("proxy"))
        if route == "GET /alerts":
            region, _ = _region_and_date(query.get("region"), None)
            timeline = store.read_json(f"{region}/alerts/timeline.json")
            if timeline is None:
                raise HttpError(404, f"no alerts for region {region!r} yet")
            return _response(200, timeline)
        if route == "GET /backtest":
            region, _ = _region_and_date(query.get("region"), None)
            report = store.read_json(f"{region}/backtest.json")
            if report is None:
                raise HttpError(404, f"no backtest for region {region!r} yet")
            return _response(200, report)
        if route == "POST /plan":
            try:
                body = json.loads(event.get("body") or "{}")
            except json.JSONDecodeError:
                raise HttpError(400, "body must be JSON")
            return _response(200, post_plan(body))
        raise HttpError(404, f"unknown route {route}")
    except HttpError as e:
        return _response(e.status, {"error": str(e)})
