"""Where ponds.json documents live.

Layout (same keys locally and in S3, under the "data/" prefix in the bucket):
    {region}/index.json              {"asOf": ["2024-01-31", "2024-02-05", ...]}
    {region}/asof/{YYYY-MM-DD}.json  a full ponds.json document (docs/data-contract.md)

DATA_DIR=<folder>  -> read from local disk (tests, local dev)
DATA_BUCKET=<name> -> read from S3 (deployed Lambda)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

CACHE_SECONDS = 300
_cache: dict[str, tuple[float, dict | None]] = {}
_s3 = None


def _s3_client():
    global _s3
    if _s3 is None:
        import boto3  # available in the Lambda runtime

        _s3 = boto3.client("s3")
    return _s3


def read_json(key: str, fresh: bool = False) -> dict | None:
    """Return the parsed document at key, or None if it does not exist. fresh=True skips the cache."""
    hit = _cache.get(key)
    if not fresh and hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]

    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        path = Path(data_dir) / key
        doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    else:
        s3 = _s3_client()
        try:
            obj = s3.get_object(Bucket=os.environ["DATA_BUCKET"], Key=f"data/{key}")
            doc = json.loads(obj["Body"].read())
        except s3.exceptions.NoSuchKey:
            doc = None

    _cache[key] = (time.time(), doc)
    return doc


def write_json(key: str, doc: dict, if_absent: bool = False) -> bool:
    """Write doc at key. With if_absent=True, only write if nothing is there yet; returns False if it was."""
    body = json.dumps(doc, ensure_ascii=False)
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        path = Path(data_dir) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "x" if if_absent else "w", encoding="utf-8") as f:
                f.write(body)
        except FileExistsError:
            return False
    else:
        s3 = _s3_client()
        extra = {"IfNoneMatch": "*"} if if_absent else {}
        try:
            s3.put_object(Bucket=os.environ["DATA_BUCKET"], Key=f"data/{key}", Body=body.encode("utf-8"),
                          ContentType="application/json; charset=utf-8", **extra)
        except s3.exceptions.ClientError as e:
            if e.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict"):
                return False
            raise
    _cache.pop(key, None)
    return True


def clear_cache() -> None:
    _cache.clear()


def resolve_as_of(region: str, as_of: str | None) -> str | None:
    """Latest published asOf date <= as_of (or the latest overall when as_of is None)."""
    index = read_json(f"{region}/index.json")
    if not index:
        return None
    dates = sorted(index.get("asOf", []))
    if as_of is not None:
        dates = [d for d in dates if d <= as_of]
    return dates[-1] if dates else None


def get_ponds_doc(region: str, as_of: str | None) -> dict | None:
    resolved = resolve_as_of(region, as_of)
    if resolved is None:
        return None
    return read_json(f"{region}/asof/{resolved}.json")
