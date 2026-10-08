"""Measurements JSON exporter module.

Formats and exports pipeline outputs according to docs/measurements-contract.md.

Who writes it: satellite pipeline (pipeline/)
Who reads it: backend snapshot builder (backend/logic/snapshot.py)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pipeline.ponds import DetectedPond, PondMeasurement
from pipeline.stac import STACScene


def build_measurements_doc(
    region_id: str,
    region_name: str,
    bbox: List[float],
    reference_date: str,
    scenes: List[dict],  # [{"date": ..., "id": ..., "status": ...}]
    ponds: List[dict],    # [{"id": ..., "lat": ..., "lon": ..., "place": ..., "refAreaHa": ..., "history": [...]}]
    et0: List[dict] | None = None,
    et0_climatology: Dict[str, float] | None = None,
    et0_forecast: List[dict] | None = None,
    generated_at: str | None = None,
) -> Dict[str, Any]:
    """Build the dictionary structure for measurements.json per docs/measurements-contract.md."""
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if et0 is None:
        et0 = []
    if et0_climatology is None:
        et0_climatology = {}

    doc: Dict[str, Any] = {
        "region": {
            "id": region_id,
            "name": region_name,
            "bbox": bbox,
        },
        "generatedAt": generated_at,
        "referenceDate": reference_date,
        "scenes": scenes,
        "et0": et0,
        "et0Climatology": et0_climatology,
    }

    if et0_forecast is not None:
        doc["et0Forecast"] = et0_forecast

    doc["ponds"] = ponds

    return doc


def export_measurements_json(doc: Dict[str, Any], output_path: Path | str) -> Path:
    """Save measurements document as nicely formatted JSON to output_path."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    json_text = json.dumps(doc, indent=2, ensure_ascii=False)
    out_p.write_text(json_text, encoding="utf-8")
    return out_p
