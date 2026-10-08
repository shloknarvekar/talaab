"""Upload ponds.json snapshots to the Talaab data bucket (and rebuild index.json).

    python backend/scripts/publish_data.py <file-or-folder> [--region latur-2024] [--bucket NAME]

- A single ponds.json file is published as data/{region}/asof/{asOf}.json (asOf read from the file).
- A folder is scanned for *.json ponds documents (e.g. data/latur-2024/asof/).
- index.json lists every asOf in the bucket for the region, so the API can resolve dates.

Bucket defaults to the DataBucketName output of the "talaab" CloudFormation stack.
"""
import argparse
import json
import sys
from pathlib import Path

import boto3

REGION_AWS = "us-west-2"


def stack_bucket() -> str:
    cfn = boto3.client("cloudformation", region_name=REGION_AWS)
    outputs = cfn.describe_stacks(StackName="talaab")["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in outputs if o["OutputKey"] == "DataBucketName")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--region", default=None, help="region id; default = region.id inside the file")
    ap.add_argument("--bucket", default=None)
    args = ap.parse_args()

    bucket = args.bucket or stack_bucket()
    s3 = boto3.client("s3", region_name=REGION_AWS)
    src = Path(args.path)
    files = sorted(src.glob("*.json")) if src.is_dir() else [src]

    regions = set()
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        if "ponds" not in doc or "asOf" not in doc:
            print(f"skip {f} (not a ponds.json document)")
            continue
        region = args.region or doc["region"]["id"]
        key = f"data/{region}/asof/{doc['asOf']}.json"
        s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(doc, ensure_ascii=False).encode("utf-8"),
                      ContentType="application/json; charset=utf-8")
        regions.add(region)
        print(f"uploaded {f.name} -> s3://{bucket}/{key}")

    for region in regions:
        prefix = f"data/{region}/asof/"
        dates = sorted(
            obj["Key"][len(prefix):-len(".json")]
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
            for obj in page.get("Contents", [])
        )
        s3.put_object(Bucket=bucket, Key=f"data/{region}/index.json",
                      Body=json.dumps({"asOf": dates}).encode("utf-8"), ContentType="application/json")
        print(f"index for {region}: {len(dates)} snapshot(s), latest {dates[-1] if dates else '-'}")

    if not regions:
        sys.exit("nothing published")


if __name__ == "__main__":
    main()
