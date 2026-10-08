"""POST /plan orchestration: instant template plan, AI plan generated in the background.

API Gateway gives a request at most 30 s, and an AI plan can take longer, so:
  1. cached AI plan for (region, asOf, language)?  -> return it, status "ready"
  2. else start the worker Lambda once (status marker in S3) -> return the template plan
     with status "generating"; the client asks again a few seconds later
  3. AI disabled, or the last attempt failed recently -> template plan, status "template"

Plans are cached per published snapshot, so Bedrock is paid at most once per snapshot and
language, whoever calls the API.
"""
from __future__ import annotations

import json
import os
import time

from api import store
from logic.plan import build_plan

RETRY_AFTER_SECONDS = 600


def plan_key(region: str, as_of: str, language: str) -> str:
    return f"{region}/plans/{as_of}-{language}.json"


def status_key(region: str, as_of: str, language: str) -> str:
    return f"{region}/plans/{as_of}-{language}.status.json"


def _ai_enabled() -> bool:
    return os.environ.get("PLAN_AI", "off") == "on" and bool(os.environ.get("PLAN_WORKER"))


def _start_worker(region: str, as_of: str, language: str) -> None:
    import boto3

    boto3.client("lambda").invoke(
        FunctionName=os.environ["PLAN_WORKER"],
        InvocationType="Event",
        Payload=json.dumps({"region": region, "asOf": as_of, "language": language}).encode(),
    )


def get_plan(doc: dict, language: str) -> dict:
    region, as_of = doc["region"]["id"], doc["asOf"]
    cached = store.read_json(plan_key(region, as_of, language), fresh=True)
    if cached:
        return {**cached, "asOf": as_of, "language": language, "status": "ready"}

    template = build_plan(doc, language)
    if not _ai_enabled():
        return {**template, "status": "template"}

    skey = status_key(region, as_of, language)
    marker = {"state": "pending", "at": int(time.time())}
    claimed = store.write_json(skey, marker, if_absent=True)
    if not claimed:
        current = store.read_json(skey, fresh=True) or {}
        age = time.time() - current.get("at", 0)
        if age < RETRY_AFTER_SECONDS:
            if current.get("state") == "failed":
                return {**template, "status": "template", "aiError": current.get("reason", "failed")}
            return {**template, "status": "generating"}
        store.write_json(skey, marker)  # stale marker: try again

    _start_worker(region, as_of, language)
    return {**template, "status": "generating"}
