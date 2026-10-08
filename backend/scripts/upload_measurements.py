"""Upload a pipeline measurements.json to S3 and recompute that region right away.

    python backend/scripts/upload_measurements.py data/latur-2026/measurements.json [--region latur-2026]

Region defaults to region.id inside the file. The scheduled job would pick the file up within
5 days anyway; this makes new data live in about a minute and prints the result.
"""
import argparse
import json
from pathlib import Path

import boto3

AWS_REGION = "us-west-2"
STACK = "talaab"


def stack_output(key: str) -> str:
    outputs = boto3.client("cloudformation", region_name=AWS_REGION).describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in outputs if o["OutputKey"] == key)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("measurements")
    ap.add_argument("--region", default=None)
    args = ap.parse_args()

    path = Path(args.measurements)
    meas = json.loads(path.read_text(encoding="utf-8"))
    for field in ("region", "scenes", "ponds"):
        if field not in meas:
            raise SystemExit(f"{path} is missing '{field}' (see docs/measurements-contract.md)")
    region = args.region or meas["region"]["id"]

    bucket = stack_output("DataBucketName")
    boto3.client("s3", region_name=AWS_REGION).put_object(
        Bucket=bucket, Key=f"data/{region}/measurements.json", Body=path.read_bytes(), ContentType="application/json")
    print(f"uploaded {path} -> s3://{bucket}/data/{region}/measurements.json "
          f"({len(meas['ponds'])} ponds, {len(meas['scenes'])} passes)")

    resp = boto3.client("lambda", region_name=AWS_REGION).invoke(
        FunctionName=stack_output("RecomputeFunctionName"), Payload=json.dumps({"regions": [region]}).encode())
    result = json.loads(resp["Payload"].read())
    if resp.get("FunctionError"):
        raise SystemExit(f"recompute failed: {result}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
