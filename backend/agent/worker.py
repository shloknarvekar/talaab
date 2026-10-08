"""Plan worker Lambda (invoked asynchronously by POST /plan).

Event: {"region": "latur-2024", "asOf": "2024-03-26", "language": "en"|"mr"}
Writes the validated AI plan to S3, or a "failed" status marker with the reason.
"""
from __future__ import annotations

import json
import time

from agent.plan_agent import write_plan
from api import store
from api.plans import plan_key, status_key


def lambda_handler(event, context):
    region, as_of, language = event["region"], event["asOf"], event["language"]
    print(json.dumps({"msg": "plan worker start", **event}))
    doc = store.read_json(f"{region}/asof/{as_of}.json")
    if doc is None:
        store.write_json(status_key(region, as_of, language), {"state": "failed", "at": int(time.time()), "reason": "snapshot not found"})
        return {"ok": False}

    started = time.time()
    try:
        plan = write_plan(doc, language)
    except Exception as e:  # Bedrock errors, quota, guard rejection: keep the template plan
        reason = f"{type(e).__name__}: {e}"[:300]
        print(json.dumps({"msg": "plan worker failed", "reason": reason}))
        store.write_json(status_key(region, as_of, language), {"state": "failed", "at": int(time.time()), "reason": reason})
        return {"ok": False, "reason": reason}

    plan["at"] = int(time.time())
    plan["seconds"] = round(time.time() - started, 1)
    store.write_json(plan_key(region, as_of, language), plan)
    print(json.dumps({"msg": "plan worker done", "seconds": plan["seconds"], "pondIds": plan["pondIds"]}))
    return {"ok": True}
