"""Local AI worker Lambda (PLAN_AI=local): an open model writes a checked briefing on top of the plan, no Bedrock.

Qwen3-1.7B (Apache-2.0, 4-bit GGUF, ~1.1 GB) runs on the Lambda's CPU with llama.cpp (llama-cpp-python, layer
built by scripts/build_layer.py --name llm-layer). The model file lives in our S3 bucket and is copied to /tmp
on a cold start (~10 s); a warm Lambda keeps it loaded. agent/briefing.py decides what the model sees and
checks every sentence it writes.

Events:
  {"region", "asOf", "language": "en"}   from POST /plan -> S3 plan (plans.plan_key) or a "failed" status marker
  {"jobs": [{"region", "asOf"}, ...]}    pre-write briefings (after a recompute); chains itself before timing out
  {"action": "fetch-model"}              once: copy the pinned model file from Hugging Face to S3 (sha256 checked)

At most one worker runs at a time (api/plans.py LOCK_KEY), so the API always keeps Lambdas free.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request

from agent.briefing import MODEL_NAME, groups_for_division, groups_for_snapshot, with_briefing, write_briefing
from api import store
from api.plans import claim_llm, plan_key, release_llm, status_key
from jobs.regions import DIVISIONS
from logic.plan import build_division_plan, build_plan

MODEL_FILE = "Qwen3-1.7B-Q4_K_M.gguf"
MODEL_URL = ("https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/"
             "d7f544eead698dbd1f15126ef60b45a1e1933222/Qwen3-1.7B-Q4_K_M.gguf")  # pinned revision
MODEL_SHA256 = "b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897"
MODEL_BYTES = 1107409472
MODEL_KEY = f"models/{MODEL_FILE}"  # outside data/: never served by the API
LOCAL_PATH = f"/tmp/{MODEL_FILE}"
MAX_TOKENS = 120
CHAIN_AFTER_SECONDS = 420  # Lambda stops at 900 s and one briefing can take ~5 min: hand the rest to a fresh invocation
_llm = None


def _model():
    global _llm
    if _llm is None:
        import boto3
        from llama_cpp import Llama

        if not (os.path.exists(LOCAL_PATH) and os.path.getsize(LOCAL_PATH) == MODEL_BYTES):
            started = time.time()
            boto3.client("s3").download_file(os.environ["DATA_BUCKET"], MODEL_KEY, LOCAL_PATH + ".part")
            os.replace(LOCAL_PATH + ".part", LOCAL_PATH)
            print(json.dumps({"msg": "model copied to /tmp", "seconds": round(time.time() - started, 1)}))
        started = time.time()
        _llm = Llama(model_path=LOCAL_PATH, n_ctx=2048, n_threads=os.cpu_count() or 2, n_batch=256, verbose=False)
        print(json.dumps({"msg": "model loaded", "seconds": round(time.time() - started, 1), "threads": os.cpu_count()}))
    return _llm


def generate(prompt: str, temperature: float, seed: int) -> str:
    out = _model()(prompt, max_tokens=MAX_TOKENS, temperature=temperature, top_p=0.8, top_k=20, seed=seed,
                   stop=["<|im_end|>", "<|endoftext|>", "\n"])
    return out["choices"][0]["text"]


def load(region: str, as_of: str) -> tuple[dict | None, bool]:
    division = region in DIVISIONS
    return store.read_json(f"{region}/division/{as_of}.json" if division else f"{region}/asof/{as_of}.json"), division


def write_plan(region: str, as_of: str, language: str = "en", gen=generate) -> dict:
    """Template plan + checked AI briefing -> S3. Raises if the snapshot is missing or the briefing is rejected."""
    doc, division = load(region, as_of)
    if doc is None:
        raise LookupError("snapshot not found")
    template = build_division_plan(doc, language) if division else build_plan(doc, language)
    started = time.time()
    briefing, rejected = write_briefing(groups_for_division(doc) if division else groups_for_snapshot(doc), gen)
    plan = {**template, "markdown": with_briefing(template["markdown"], briefing), "source": "local-ai",
            "model": MODEL_NAME, "briefing": briefing, "rejectedDrafts": sum(len(v) for v in rejected.values()),
            "at": int(time.time()), "seconds": round(time.time() - started, 1)}
    store.write_json(plan_key(region, as_of, language), plan)
    return plan


def _one(region: str, as_of: str, language: str, gen=generate) -> dict:
    try:
        plan = write_plan(region, as_of, language, gen)
    except Exception as e:  # rejected briefing, missing snapshot, model error: the template plan stays
        reason = f"{type(e).__name__}: {e}"[:300]
        store.write_json(status_key(region, as_of, language), {"state": "failed", "at": int(time.time()), "reason": reason})
        print(json.dumps({"msg": "briefing failed", "region": region, "asOf": as_of, "reason": reason}))
        return {"region": region, "asOf": as_of, "ok": False, "reason": reason}
    print(json.dumps({"msg": "briefing done", "region": region, "asOf": as_of, "seconds": plan["seconds"],
                      "rejectedDrafts": plan["rejectedDrafts"]}))
    return {"region": region, "asOf": as_of, "ok": True, "seconds": plan["seconds"]}


def run_jobs(jobs: list[dict], context=None, gen=generate, invoke=None) -> list[dict]:
    """Pre-write briefings one after another (skipping cached ones); chain the rest before the Lambda times out."""
    started, done = time.time(), []
    for i, job in enumerate(jobs):
        if context is not None and time.time() - started > CHAIN_AFTER_SECONDS:
            (invoke or _invoke_self)(context.function_name, {"jobs": jobs[i:]})
            print(json.dumps({"msg": "chained", "remaining": len(jobs) - i}))
            return done
        if store.read_json(plan_key(job["region"], job["asOf"], "en"), fresh=True):
            continue
        claim_llm(f"jobs/{job['region']}")  # refresh the slot for each job
        done.append(_one(job["region"], job["asOf"], "en", gen))
    return done


def _invoke_self(name: str, payload: dict) -> None:
    import boto3

    boto3.client("lambda").invoke(FunctionName=name, InvocationType="Event", Payload=json.dumps(payload).encode())


def fetch_model() -> dict:
    """Stream the pinned model file from Hugging Face into S3, checking size and sha256 on the way."""
    import boto3

    digest, size = hashlib.sha256(), 0

    class Hashing:
        def __init__(self, raw):
            self.raw = raw

        def read(self, n=-1):
            nonlocal size
            chunk = self.raw.read(n)
            digest.update(chunk)
            size += len(chunk)
            return chunk

    s3, bucket = boto3.client("s3"), os.environ["DATA_BUCKET"]
    with urllib.request.urlopen(MODEL_URL, timeout=60) as r:  # noqa: S310 (fixed https URL, pinned revision)
        s3.upload_fileobj(Hashing(r), bucket, MODEL_KEY)
    if size != MODEL_BYTES or digest.hexdigest() != MODEL_SHA256:
        s3.delete_object(Bucket=bucket, Key=MODEL_KEY)
        raise ValueError(f"model check failed: {size} bytes, sha256 {digest.hexdigest()}")
    return {"ok": True, "bytes": size, "sha256": MODEL_SHA256}


def lambda_handler(event, context):
    print(json.dumps({"msg": "llm worker start", **{k: v for k, v in event.items() if k != "jobs"},
                      "jobs": len(event.get("jobs", []))}))
    if event.get("action") == "fetch-model":
        return fetch_model()
    try:
        if "jobs" in event:
            return {"done": run_jobs(event["jobs"], context)}
        return _one(event["region"], event["asOf"], event.get("language", "en"))
    finally:
        release_llm()
