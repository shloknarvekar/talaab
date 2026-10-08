"""Talaab HTTP API (API Gateway HTTP API, payload format 2.0).

GET  /ponds?region=latur-2024&asOf=YYYY-MM-DD   -> ponds.json document
GET  /ponds/{id}?region=...&asOf=...            -> one pond
POST /plan {region, asOf, language: en|mr}      -> {markdown, pondIds, source, status}
GET  /backtest?region=latur-2024                -> how well past predictions matched reality

asOf picks the latest published snapshot on or before that date, so a replay never
shows data from after the date the user chose.
"""
from __future__ import annotations

import json
import os
import re

from api import store
from api.plans import get_plan

DEFAULT_REGION = os.environ.get("DEFAULT_REGION", "latur-2024")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REGION_RE = re.compile(r"^[a-z0-9-]{1,40}$")
POND_RE = re.compile(r"^P\d{3,4}$")


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


def get_ponds(query: dict) -> dict:
    region, as_of = _region_and_date(query.get("region"), query.get("asOf"))
    return _load(region, as_of)


def get_pond(pond_id: str, query: dict) -> dict:
    if not POND_RE.match(pond_id or ""):
        raise HttpError(400, "pond id must look like P001")
    region, as_of = _region_and_date(query.get("region"), query.get("asOf"))
    doc = _load(region, as_of)
    for pond in doc["ponds"]:
        if pond["id"] == pond_id:
            return {**pond, "asOf": doc["asOf"], "region": doc["region"]["id"]}
    raise HttpError(404, f"pond {pond_id} not found in {region} as of {doc['asOf']}")


def post_plan(body: dict) -> dict:
    region, as_of = _region_and_date(body.get("region"), body.get("asOf"))
    language = body.get("language", "en")
    if language not in ("en", "mr"):
        raise HttpError(400, "language must be 'en' or 'mr'")
    doc = _load(region, as_of)
    return get_plan(doc, language)


def lambda_handler(event, context):
    route = event.get("routeKey", "")
    query = event.get("queryStringParameters") or {}
    print(json.dumps({"route": route, "query": query}))
    try:
        if route == "GET /ponds":
            return _response(200, get_ponds(query))
        if route == "GET /ponds/{id}":
            return _response(200, get_pond((event.get("pathParameters") or {}).get("id"), query))
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
