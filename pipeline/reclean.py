"""Re-apply the quality rules to an existing measurements.json (no satellite download needed).

    python -m pipeline.reclean data/latur-2024/measurements.json [--out PATH]

Every rule works on the measured areas, so improving cleanup does not require re-reading
Sentinel-2. Overwrites the file unless --out is given, and records what was changed under
"quality" and "excludedPonds" so the result is auditable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.cleanup import apply_quality_rules


def reclean(doc: dict) -> dict:
    precip = {x["date"]: x.get("precip") or 0.0 for x in doc.get("et0") or []}
    scenes, kept, excluded, report = apply_quality_rules(doc["scenes"], doc["ponds"], precip, doc["referenceDate"])
    return {**doc, "scenes": scenes, "ponds": kept,
            "excludedPonds": doc.get("excludedPonds", []) + excluded, "quality": report}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("measurements")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    src = Path(args.measurements)
    doc = reclean(json.loads(src.read_text(encoding="utf-8")))
    out = Path(args.out) if args.out else src
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out}: {doc['quality']}")
    for e in doc["excludedPonds"]:
        print(f"  excluded {e['id']} ({e['refAreaHa']} ha {e.get('place', '')}): {e['reason']}")


if __name__ == "__main__":
    main()
