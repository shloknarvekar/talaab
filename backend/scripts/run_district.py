"""Run the whole-district pipeline on AWS (Step Functions -> one Lambda per grid cell -> merge -> recompute).

    python backend/scripts/run_district.py [--region latur-district-2024|<slug>-district-2026] [--cells c03-02,c03-03] [--wait]
    python backend/scripts/run_district.py --marathwada [--wait]   # all 8 districts, live (what the schedule runs)

Starts the talaab-district state machine (the grid step lists the cells). latur-district-2024 is the
2024 replay; latur-district-2026 is the live season (end = today), the same input EventBridge
Scheduler sends every 5 days. With --wait it follows the execution, then prints the run summary
(data/<region>/run.json) and the measured Lambda cost.
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
RUNS = {
    "latur-district-2024": {"region": "latur-district-2024", "name": "Latur district (2024 replay)", "boundary": "latur-district",
                            "start": "2024-01-01", "end": "2024-06-30", "referenceDate": "2024-01-16", "maxCloud": 20},
}
# Live season for every Marathwada district; keep in sync with the LiveMarathwada schedule input in backend/template.yaml
LIVE = {"start": "2026-09-01", "end": "today", "referenceDate": "2026-09-27", "maxCloud": 45}
MARATHWADA = [("latur", "Latur"), ("beed", "Beed"), ("dharashiv", "Dharashiv"), ("nanded", "Nanded"), ("parbhani", "Parbhani"),
              ("hingoli", "Hingoli"), ("jalna", "Jalna"), ("sambhajinagar", "Chhatrapati Sambhajinagar")]
for _slug, _name in MARATHWADA:
    RUNS[f"{_slug}-district-2026"] = {"region": f"{_slug}-district-2026", "name": f"{_name} district (live, 2026)",
                                      "boundary": f"{_slug}-district", **LIVE}
ARM_PRICE_GB_S = 0.0000133334  # Lambda arm64 on-demand, us-west-2 (USD); free tier covers 400,000 GB-s/month


def stack_output(key: str) -> str:
    outs = boto3.client("cloudformation", region_name=AWS_REGION).describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in outs if o["OutputKey"] == key)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="latur-district-2024", choices=sorted(RUNS))
    ap.add_argument("--cells", help="comma-separated cell ids (default: all cells touching the district)")
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--marathwada", action="store_true", help="all Marathwada districts, live, one after another")
    args = ap.parse_args()
    if args.marathwada:
        return run_marathwada(args.wait)

    run_input = dict(RUNS[args.region])
    boundary = load_boundary(run_input["boundary"])
    cells = grid_cells(boundary)
    if args.cells:
        run_input["onlyCells"] = args.cells.split(",")
        cells = [c for c in cells if c["id"] in set(run_input["onlyCells"])]
    print(f"{run_input['name']}: {area_km2(boundary['geometry']):,.0f} km2, {len(cells)} cells")

    sfn = boto3.client("stepfunctions", region_name=AWS_REGION)
    arn = sfn.start_execution(stateMachineArn=stack_output("DistrictStateMachineArn"),
                              name=f"{run_input['region']}-{time.strftime('%Y%m%d-%H%M%S')}",
                              input=json.dumps(run_input))["executionArn"]
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
    save_run(run_input["region"], run, round((desc["stopDate"] - desc["startDate"]).total_seconds()))


def save_run(region: str, run: dict, wall_seconds: int | None) -> None:
    gb_s = run["cellSeconds"] * 2.0 + run["mergeSeconds"] * 1.0  # cell 2048 MB, merge 1024 MB
    if wall_seconds is not None:
        run["wallSeconds"] = wall_seconds
    run.update(lambdaGbSeconds=round(gb_s), lambdaCostUsdWithoutFreeTier=round(gb_s * ARM_PRICE_GB_S, 4))
    print(region, json.dumps(run))
    out = ROOT / "data" / region / "run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")


def run_marathwada(wait: bool) -> None:
    """Start the talaab-marathwada workflow with the schedule's input (every district, live season)."""
    run_input = {**LIVE, "districts": [{"region": f"{s}-district-2026", "name": f"{n} district (live, 2026)",
                                        "boundary": f"{s}-district"} for s, n in MARATHWADA]}
    sfn = boto3.client("stepfunctions", region_name=AWS_REGION)
    arn = sfn.start_execution(stateMachineArn=stack_output("MarathwadaStateMachineArn"),
                              name=f"marathwada-{time.strftime('%Y%m%d-%H%M%S')}", input=json.dumps(run_input))["executionArn"]
    print("started", arn)
    if not wait:
        return
    started = time.time()
    while (desc := sfn.describe_execution(executionArn=arn))["status"] == "RUNNING":
        time.sleep(30)
        print(f"  running {time.time() - started:.0f} s")
    print("status", desc["status"], f"after {time.time() - started:.0f} s")
    if desc["status"] != "SUCCEEDED":
        sys.exit(desc.get("error", "") + " " + desc.get("cause", ""))
    totals = {"cells": 0, "pondsKept": 0, "lambdaGbSeconds": 0}
    for r in json.loads(desc["output"])["results"]:
        if r.get("status") != "SUCCEEDED":
            print(r["region"], "FAILED", json.dumps(r.get("error"))[:300])
            continue
        save_run(r["region"], r["run"], None)
        for k in ("cells", "pondsKept"):
            totals[k] += r["run"][k]
        totals["lambdaGbSeconds"] += r["run"]["lambdaGbSeconds"]
    totals.update(wallSeconds=round((desc["stopDate"] - desc["startDate"]).total_seconds()),
                  lambdaCostUsdWithoutFreeTier=round(totals["lambdaGbSeconds"] * ARM_PRICE_GB_S, 4))
    print("MARATHWADA", json.dumps(totals))


if __name__ == "__main__":
    main()
