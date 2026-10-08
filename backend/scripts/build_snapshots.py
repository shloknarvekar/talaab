"""measurements.json -> one ponds.json snapshot per as-of date (honest backtest: each uses only past data).

    python backend/scripts/build_snapshots.py data/latur-2024/measurements.json [--as-of 2024-03-26 ...] [--out DIR]

Default as-of dates: every scene date from 20 days after the first pass (enough points for a fit).
Default output: <measurements folder>/asof/{date}.json, ready for publish_data.py.
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on the path

from logic.snapshot import build_snapshot  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("measurements")
    ap.add_argument("--as-of", nargs="*", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    src = Path(args.measurements)
    meas = json.loads(src.read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else src.parent / "asof"
    out.mkdir(parents=True, exist_ok=True)

    if args.as_of:
        dates = args.as_of
    else:
        first = date.fromisoformat(meas["scenes"][0]["date"])
        dates = [s["date"] for s in meas["scenes"] if date.fromisoformat(s["date"]) >= first + timedelta(days=20)]

    for d in dates:
        snap = build_snapshot(meas, d)
        (out / f"{d}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        counts = {}
        for p in snap["ponds"]:
            counts[p["status"]] = counts.get(p["status"], 0) + 1
        flagged = [p["id"] for p in snap["ponds"] if p["flag"]]
        print(f"{d}: {counts} flagged={flagged} sun={snap['sunShareMm']}mm")
    print(f"{len(dates)} snapshot(s) -> {out}")


if __name__ == "__main__":
    main()
