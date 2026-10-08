"""Backtest a region and write the report (Markdown for the writeup, JSON for the web/API).

    python backend/scripts/run_backtest.py data/latur-2024/measurements.json [--upload]

Writes data/{region}/backtest.json and docs/backtest-{region}.md. --upload also puts the JSON in
S3 so GET /backtest?region=... serves it.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on the path

from logic.backtest import backtest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def pct(x):
    return "n/a" if x is None else f"{round(100 * x)}%"


def days(x):
    return "n/a" if x is None else f"{x:g} days"


def markdown(r: dict) -> str:
    s, n = r["summary"], r["variants"]["noHeatAdjustment"]
    ev = r["evaluated"]
    lines = [
        f"# Backtest: {r['region']['name']}",
        "",
        "> **Synthetic data.** These numbers test the scoring code, not the method: the synthetic ponds were "
        "built to shrink with the heat, so the heat adjustment wins by construction. Re-run on real data."
        if r["synthetic"] else
        "> Every prediction below was made using only satellite passes and weather available on that date.",
        "",
        f"Replayed **{ev['snapshots']} satellite passes** ({ev['from']} to {ev['to']}) for **{ev['ponds']} ponds**; "
        f"**{ev['pondsThatDried']}** of them dried up during the season.",
        "",
        "| Question | Talaab | Without heat adjustment |",
        "|---|---|---|",
        f"| Actual dry date inside our predicted range | **{pct(s['rangeHitRate'])}** ({s['rangeHits']} of {s['rangeHits'] + s['rangeMisses'] + s['tooEarly']}) | {pct(n['rangeHitRate'])} |",
        f"| Median error of the likely date (+ = we said later) | {days(s['medianErrorDays'])} | {days(n['medianErrorDays'])} |",
        f"| \"Critical\" calls that came true within 30 days | **{pct(s['criticalPrecision'])}** ({s['criticalCalls']} calls) | {pct(n['criticalPrecision'])} |",
        f"| Ponds about to dry (≤ 30 days) that we had marked critical | **{pct(s['criticalRecall'])}** | {pct(n['criticalRecall'])} |",
        f"| Median warning before a pond dried | **{days(s['medianLeadDays'])}** ({s['pondsWarnedInAdvance']} ponds) | {days(n['medianLeadDays'])} |",
        f"| Predicted dry, but the pond survived the season | {s['tooEarly']} | {n['tooEarly']} |",
        "",
        "## Ponds that dried",
        "",
        "| Pond | Actually dried between | First marked critical | Warning |",
        "|---|---|---|---|",
    ]
    for p in r["ponds"]:
        if p["actualDry"]:
            lines.append(f"| {p['id']} | {p['actualDry']['from']} and {p['actualDry']['to']} | "
                         f"{p['firstCritical'] or 'never'} | {days(p['leadDays']) if p['leadDays'] is not None else '-'} |")
    lines += [
        "",
        "## How this is scored",
        "",
        "- A pond counts as dry at the first clear pass below 5% of its largest area that stays below for the rest of the season. "
        "Passes are about 5 days apart, so the true dry date is a window, not a day.",
        "- For each pass date we rebuild the forecast exactly as Talaab would have on that day, then compare.",
        "- A range is a hit if it overlaps the actual dry window. Ponds that never dried are only judged when we predicted they would dry before the season ended.",
        "- \"Without heat adjustment\" is the same model with the expected-evaporation scaling switched off.",
        "",
        "Data: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search); Open-Meteo (CC BY 4.0).",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("measurements")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args()

    meas = json.loads(Path(args.measurements).read_text(encoding="utf-8"))
    r = backtest(meas, args.start, args.end)
    region = meas["region"]["id"]

    out_json = ROOT / "data" / region / "backtest.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(r, indent=1), encoding="utf-8")
    out_md = ROOT / "docs" / f"backtest-{region}.md"
    out_md.write_text(markdown(r), encoding="utf-8")
    print(f"wrote {out_json}\nwrote {out_md}")
    print(json.dumps(r["summary"], indent=1))

    if args.upload:
        import boto3

        cfn = boto3.client("cloudformation", region_name="us-west-2")
        outputs = cfn.describe_stacks(StackName="talaab")["Stacks"][0]["Outputs"]
        bucket = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "DataBucketName")
        boto3.client("s3", region_name="us-west-2").put_object(
            Bucket=bucket, Key=f"data/{region}/backtest.json", Body=out_json.read_bytes(), ContentType="application/json")
        print(f"uploaded -> s3://{bucket}/data/{region}/backtest.json")


if __name__ == "__main__":
    main()
