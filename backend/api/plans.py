"""POST /plan orchestration: instant template plan, AI plan generated in the background.

API Gateway gives a request at most 30 s, and an AI plan can take longer, so:
  1. cached AI plan for (region, asOf, language)?  -> return it, status "ready"
  2. else start the worker Lambda once (status marker in S3) -> return the template plan
     with status "generating"; the client asks again a few seconds later
  3. AI disabled, or the last attempt failed recently -> template plan, status "template"

PLAN_AI selects the writer: "on" = Bedrock (agent/worker.py, whole plan, EN + MR), "local" = an open model in
our own Lambda (agent/llm_worker.py: a checked English briefing on top of the template plan, districts and the
division), "off" = template only. The local writer needs a 3 GB Lambda for a minute or two and the account
runs 10 Lambdas at once, so at most ONE runs at a time (LOCK_KEY); other requests get the template meanwhile.

Plans are cached per published snapshot, so the AI runs at most once per snapshot and language, whoever calls.
"""
from __future__ import annotations

import json
import os
import time

from api import store
from jobs.regions import DIVISIONS
from logic.plan import build_plan

RETRY_AFTER_SECONDS = 600
LOCK_KEY = "_ai/llm-lock.json"
LOCK_SECONDS = 900  # the worker Lambda's time limit: a crashed worker frees the lock after this
LOCAL_LANGUAGES = ("en",)  # a 1.7B model writes poor Marathi: Marathi stays the template plan


def plan_key(region: str, as_of: str, language: str) -> str:
    return f"{region}/plans/{as_of}-{language}.json"


def status_key(region: str, as_of: str, language: str) -> str:
    return f"{region}/plans/{as_of}-{language}.status.json"


def _mode() -> str:
    mode = os.environ.get("PLAN_AI", "off")
    return mode if mode in ("on", "local") and os.environ.get("PLAN_WORKER") else "off"


def _ai_for(region: str, language: str) -> bool:
    mode = _mode()
    if mode == "local":
        return language in LOCAL_LANGUAGES
    return mode == "on" and region not in DIVISIONS  # the Bedrock agent's tools read pond snapshots only


def claim_llm(owner: str) -> bool:
    """Take the single local-model slot (free if absent, released, or older than LOCK_SECONDS)."""
    if store.write_json(LOCK_KEY, {"at": int(time.time()), "owner": owner}, if_absent=True):
        return True
    current = store.read_json(LOCK_KEY, fresh=True) or {}
    if time.time() - current.get("at", 0) > LOCK_SECONDS:
        store.write_json(LOCK_KEY, {"at": int(time.time()), "owner": owner})
        return True
    return False


def release_llm() -> None:
    store.write_json(LOCK_KEY, {"at": 0, "owner": None})


def _start_worker(region: str, as_of: str, language: str) -> None:
    import boto3

    boto3.client("lambda").invoke(
        FunctionName=os.environ["PLAN_WORKER"],
        InvocationType="Event",
        Payload=json.dumps({"region": region, "asOf": as_of, "language": language}).encode(),
    )


def get_plan(doc: dict, language: str, template: dict | None = None, region: str | None = None) -> dict:
    """doc: a ponds.json snapshot, or (with region and template) a division summary."""
    region, as_of = region or doc["region"]["id"], doc["asOf"]
    cached = store.read_json(plan_key(region, as_of, language), fresh=True)
    if cached:
        return {**cached, "asOf": as_of, "language": language, "status": "ready"}

    template = template or build_plan(doc, language)
    if not _ai_for(region, language):
        return {**template, "status": "template"}

    skey = status_key(region, as_of, language)
    current = store.read_json(skey, fresh=True)
    if current and time.time() - current.get("at", 0) < RETRY_AFTER_SECONDS:
        if current.get("state") == "failed":
            return {**template, "status": "template", "aiError": current.get("reason", "failed")}
        return {**template, "status": "generating"}

    local = _mode() == "local"
    if local and not claim_llm(f"{region}/{as_of}-{language}"):
        return {**template, "status": "template", "aiNote": "the AI writer is busy with another plan; try again in a minute"}
    marker = {"state": "pending", "at": int(time.time())}
    if current is None and not store.write_json(skey, marker, if_absent=True):
        if local:
            release_llm()  # another request started this plan a moment ago and holds its own slot
        return {**template, "status": "generating"}
    if current is not None:
        store.write_json(skey, marker)  # stale marker: try again
    _start_worker(region, as_of, language)
    return {**template, "status": "generating"}
