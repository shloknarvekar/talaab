"""Pre-generate and cache AI plans (Bedrock) for chosen demo dates, so the Plan tab is instant.

    python backend/scripts/pregenerate_plans.py                      # latest date of each region, EN + MR
    python backend/scripts/pregenerate_plans.py --dates 2024-04-05 2024-04-15 --regions latur-2024
    python backend/scripts/pregenerate_plans.py --yes                # skip the cost confirmation

Each plan is generated once by the plan-worker Lambda (Strands + Bedrock, number guard) and cached in
S3; afterwards POST /plan returns it instantly with status "ready" (even with PlanAI=off, because a
cached AI plan is always served first). Plans already cached are skipped. Needs Bedrock access
(python backend/scripts/check_bedrock.py). Hard cap: --max plans (default 8).
"""
import argparse
import json
import sys
import urllib.request

import boto3

AWS_REGION = "us-west-2"
API = "https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com"
EST_USD_PER_PLAN = 0.12  # ~10k tokens in + ~3k out on Claude Opus 5.5


def regions():
    with urllib.request.urlopen(f"{API}/regions", timeout=20) as r:  # noqa: S310
        return {x["id"]: x for x in json.loads(r.read())["regions"] if not x.get("synthetic")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", nargs="*")
    ap.add_argument("--dates", nargs="*", help="as-of dates; default = latest of each region")
    ap.add_argument("--languages", nargs="*", default=["en", "mr"])
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    available = regions()
    jobs = []
    for rid in args.regions or list(available):
        if rid not in available:
            sys.exit(f"unknown region {rid}; available: {', '.join(available)}")
        for d in args.dates or [available[rid]["last"]]:
            if d not in available[rid]["dates"]:
                sys.exit(f"{rid} has no snapshot for {d}")
            jobs += [(rid, d, lang) for lang in args.languages]

    cfn = boto3.client("cloudformation", region_name=AWS_REGION)
    outputs = {o["OutputKey"]: o["OutputValue"] for o in cfn.describe_stacks(StackName="talaab")["Stacks"][0]["Outputs"]}
    bucket = outputs["DataBucketName"]
    s3 = boto3.client("s3", region_name=AWS_REGION)

    def cached(rid, d, lang):
        try:
            s3.head_object(Bucket=bucket, Key=f"data/{rid}/plans/{d}-{lang}.json")
            return True
        except s3.exceptions.ClientError:
            return False

    missing = [j for j in jobs if not cached(*j)]
    todo = missing[: args.max]
    print(f"{len(jobs)} plan(s) requested, {len(jobs) - len(missing)} already cached, {len(todo)} to generate "
          f"(cap {args.max}). Estimated cost ~${EST_USD_PER_PLAN * len(todo):.2f}, paid from credits.")
    if not todo:
        return
    if not args.yes and input("Generate now? [y/N] ").strip().lower() != "y":
        sys.exit("cancelled")

    lam = boto3.client("lambda", region_name=AWS_REGION)
    for rid, d, lang in todo:
        resp = lam.invoke(FunctionName="talaab-plan-worker", Payload=json.dumps({"region": rid, "asOf": d, "language": lang}).encode())
        result = json.loads(resp["Payload"].read())
        print(f"  {rid} {d} {lang}: {'OK' if result.get('ok') else 'FAILED ' + str(result.get('reason'))}")


if __name__ == "__main__":
    main()
