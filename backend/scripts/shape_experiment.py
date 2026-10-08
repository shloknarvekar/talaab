"""Run the pre-registered shape experiment (docs/model-experiment.md) and apply its decision rule.

    python backend/scripts/shape_experiment.py

Candidates L (linear), S (sqrt / cone) and A (auto per pond) are backtested on synthetic, Latur 2024
(development) and Latur 2023 (held-out). Only the 2023 numbers decide, using the rule written down
before the experiment was run.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "scripts"))

import logic.countdown as cd  # noqa: E402
from logic.backtest import evaluate  # noqa: E402
from synth_measurements import generate  # noqa: E402

CANDIDATES = {"L": "linear", "S": "sqrt", "A": "auto"}
KEYS = ["criticalRecall", "criticalPrecision", "medianAbsErrorDays", "tooEarly", "rangeHitRate", "medianLeadDays"]


def load(name):
    path = ROOT / "data" / name / "measurements.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def run(meas):
    out = {}
    for label, shape in CANDIDATES.items():
        cd.SHAPE = shape
        out[label] = evaluate(meas)["summary"]
    cd.SHAPE = "linear"
    return out


def qualifies(c, base):
    """The decision rule from docs/model-experiment.md, verbatim."""
    pts = lambda x: 100 * (x or 0)  # noqa: E731
    no_recall_drop = pts(c["criticalRecall"]) >= pts(base["criticalRecall"]) - 3
    no_precision_drop = pts(c["criticalPrecision"]) >= pts(base["criticalPrecision"]) - 3
    improves = ((c["medianAbsErrorDays"] or 1e9) < (base["medianAbsErrorDays"] or 1e9)) or (c["tooEarly"] < base["tooEarly"])
    range_ok = pts(c["rangeHitRate"]) >= pts(base["rangeHitRate"]) - 5
    return no_recall_drop and no_precision_drop and improves and range_ok


def main():
    datasets = {"synthetic": generate(), "latur-2024 (dev)": load("latur-2024"), "latur-2023 (HELD-OUT)": load("latur-2023")}
    results = {}
    for name, meas in datasets.items():
        if meas is None:
            print(f"{name}: no data, skipped")
            continue
        results[name] = run(meas)
        print(f"\n== {name}")
        print(f"{'':4}" + "".join(f"{k:>20}" for k in KEYS))
        for label, s in results[name].items():
            print(f"{label:4}" + "".join(f"{str(s[k]):>20}" for k in KEYS))

    held = results.get("latur-2023 (HELD-OUT)")
    if not held:
        sys.exit("\nheld-out 2023 data missing: no decision")
    base = held["L"]
    winners = [c for c in ("S", "A") if qualifies(held[c], base)]
    print("\nDecision (held-out 2023, pre-registered rule):")
    for c in ("S", "A"):
        print(f"  {c}: {'qualifies' if c in winners else 'does not qualify'}")
    choice = min(winners, key=lambda c: held[c]["medianAbsErrorDays"] or 1e9) if winners else "L"
    print(f"  -> adopt {choice} ({CANDIDATES[choice]})")


if __name__ == "__main__":
    main()
