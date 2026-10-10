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


_table = None


def _plain(value):
    """DynamoDB returns numbers as Decimal: back to int/float for JSON."""
    from decimal import Decimal

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def get_latest_pond(region: str, pond_id: str) -> dict | None:
    """One pond's latest state from the DynamoDB Ponds table (pk regionId, sk pondId), written by recompute
    after every run: a single-item read instead of loading the whole district snapshot from S3.
    None when no table is configured (local runs, tests) or the pond isn't there."""
    global _table
    table_name = os.environ.get("PONDS_TABLE")
    if not table_name or os.environ.get("DATA_DIR"):
        return None
    if _table is None:
        import boto3

        _table = boto3.resource("dynamodb").Table(table_name)
    item = _table.get_item(Key={"regionId": region, "pondId": pond_id}).get("Item")
    if not item:
        return None
    item = _plain(item)
    item["id"] = item.pop("pondId")
    item.pop("regionId", None)
    item.pop("updatedAt", None)
    return item


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


def list_keys(prefix: str) -> list[str]:
    """Keys under prefix (relative to the data root), sorted."""
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        root = Path(data_dir)
        base = root / prefix
        if not base.exists():
            return []
        return sorted(p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file())
    s3 = _s3_client()
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=os.environ["DATA_BUCKET"], Prefix=f"data/{prefix}"):
        keys.extend(obj["Key"][len("data/"):] for obj in page.get("Contents", []))
    return sorted(keys)


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
