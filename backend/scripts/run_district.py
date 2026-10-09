"""Run the whole-district pipeline on AWS (Step Functions -> one Lambda per grid cell -> merge -> recompute).

    python backend/scripts/run_district.py [--cells c03-02,c03-03] [--wait]

Starts the talaab-district state machine for Latur district, 2024 replay. With --wait it follows the
execution, then prints the run summary (data/<region>/run.json) and the measured Lambda cost.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.district import area_km2, grid_cells, load_boundary  # noqa: E402

AWS_REGION = "us-west-2"
STACK = "talaab"
RUN = {"region": "latur-district-2024", "name": "Latur district (2024 replay)", "boundary": "latur-district",
       "start": "2024-01-01", "end": "2024-06-30", "referenceDate": "2024-01-16"}
ARM_PRICE_GB_S = 0.0000133334  # Lambda arm64 on-demand, us-west-2 (USD); free tier covers 400,000 GB-s/month


def stack_output(key: str) -> str:
    outs = boto3.client("cloudformation", region_name=AWS_REGION).describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in outs if o["OutputKey"] == key)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", help="comma-separated cell ids (default: all cells touching the district)")
    ap.add_argument("--wait", action="store_true")
    args = ap.parse_args()

    boundary = load_boundary(RUN["boundary"])
    cells = grid_cells(boundary)
    if args.cells:
        keep = set(args.cells.split(","))
        cells = [c for c in cells if c["id"] in keep]
    print(f"{RUN['name']}: {area_km2(boundary['geometry']):,.0f} km2, {len(cells)} cells")

    sfn = boto3.client("stepfunctions", region_name=AWS_REGION)
    arn = sfn.start_execution(stateMachineArn=stack_output("DistrictStateMachineArn"),
                              name=f"{RUN['region']}-{time.strftime('%Y%m%d-%H%M%S')}",
                              input=json.dumps({**RUN, "cells": cells}))["executionArn"]
    print("started", arn)
    if not args.wait:
        return

    started = time.time()
    while (desc := sfn.describe_execution(executionArn=arn))["status"] == "RUNNING":
        time.sleep(30)
        print(f"  running {time.time() - started:.0f} s")
    print("status", desc["status"], f"after {time.time() - started:.0f} s")
    if desc["status"] != "SUCCEEDED":
        sys.exit(desc.get("error", "") + " " + desc.get("cause", ""))

    run = json.loads(desc["output"])
    gb_s = run["cellSeconds"] * 2.0 + run["mergeSeconds"] * 1.0  # cell 2048 MB, merge 1024 MB
    run.update(wallSeconds=round((desc["stopDate"] - desc["startDate"]).total_seconds()), lambdaGbSeconds=round(gb_s),
               lambdaCostUsdWithoutFreeTier=round(gb_s * ARM_PRICE_GB_S, 4))
    print(json.dumps(run, indent=2))
    out = ROOT / "data" / RUN["region"] / "run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
