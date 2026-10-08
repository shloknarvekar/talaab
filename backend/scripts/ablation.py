"""Ablation: score each data-quality / fit change separately on the backtest (reproduces docs/data-quality.md).

Reads the original pipeline output from git (commit 8fb2893) so the 'before' row is always reproducible.
"""
import json, sys
ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT))
import logic.countdown as cd
from logic.backtest import backtest
from pipeline.reclean import reclean
import subprocess
RAW_COMMIT = "8fb2893"  # Nikhil's original pipeline output, before the quality rules
raw = json.loads(subprocess.check_output(["git", "-C", str(ROOT), "show", f"{RAW_COMMIT}:data/latur-2024/measurements.json"]))
clean = reclean(raw)
sys.path.insert(0, str(ROOT / "backend/scripts")); from synth_measurements import generate
syn = generate()
robust = cd.robust_fit
keys = ["rangeHitRate", "medianAbsErrorDays", "criticalPrecision", "criticalRecall", "medianLeadDays", "pondsWarnedInAdvance", "tooEarly"]
def run(name, meas, fit):
    cd.robust_fit = fit
    r = backtest(meas); s = r["summary"]
    print(f"{name:34} dried={r['evaluated']['pondsThatDried']:2} " + " ".join(f"{k}={s[k]}" for k in keys) + f" | noHeat hit={r['variants']['noHeatAdjustment']['rangeHitRate']}")
run("A real raw   + OLS (v1 baseline)", raw, cd.linear_fit)
run("B real clean + OLS", clean, cd.linear_fit)
run("C real raw   + robust", raw, robust)
run("D real clean + robust (proposed)", clean, robust)
run("S synthetic  + OLS", syn, cd.linear_fit)
run("S synthetic  + robust", syn, robust)
