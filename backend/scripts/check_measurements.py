"""Check a measurements.json before uploading (no AWS needed).

    python backend/scripts/check_measurements.py data/latur-2024/measurements.json [--live]

Exit code 0 = OK to upload (warnings are printed but allowed), 1 = errors to fix.
Live regions (mode "live" in backend/jobs/regions.py) get relaxed weather checks automatically, because
the recompute job fetches their weather; --live forces that for a region id not listed there.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on the path

from jobs.regions import REGIONS  # noqa: E402
from logic.validate import validate_measurements  # noqa: E402


def check(path: Path, live: bool) -> dict:
    try:
        meas = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"errors": [f"cannot read {path}: {e}"], "warnings": [], "stats": {}}
    # Same rule as upload_measurements.py: a known region's mode decides; --live forces live checks.
    region = (meas.get("region") or {}).get("id")
    mode = "live" if live else REGIONS.get(region, {}).get("mode", "replay")
    return validate_measurements(meas, mode=mode)


def report(result: dict) -> None:
    for k, v in result["stats"].items():
        print(f"  {k}: {v}")
    for w in result["warnings"][:30]:
        print(f"  WARNING  {w}")
    if len(result["warnings"]) > 30:
        print(f"  ... and {len(result['warnings']) - 30} more warnings")
    for e in result["errors"][:30]:
        print(f"  ERROR    {e}")
    print("OK to upload" if not result["errors"] else f"{len(result['errors'])} error(s): fix before uploading")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("measurements")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    res = check(Path(args.measurements), args.live)
    report(res)
    sys.exit(1 if res["errors"] else 0)
