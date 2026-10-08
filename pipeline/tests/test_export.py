"""Tests for pipeline/export.py measurements export module."""

import json
from pathlib import Path
from pipeline.export import build_measurements_doc, export_measurements_json


def test_build_measurements_doc():
    doc = build_measurements_doc(
        region_id="latur-2024",
        region_name="Latur (2024 replay)",
        bbox=[76.47, 18.33, 76.62, 18.48],
        reference_date="2024-01-16",
        scenes=[{"date": "2024-01-16", "id": "S2B_43QFA_20240116_0_L2A", "status": "ok"}],
        ponds=[
            {
                "id": "P001",
                "lat": 18.41,
                "lon": 76.55,
                "place": "near Bhadgaon",
                "refAreaHa": 15.0,
                "history": [{"date": "2024-01-16", "areaHa": 15.0, "valid": True}],
            }
        ],
        et0=[{"date": "2024-01-16", "et0": 3.5, "precip": 0.0}],
        et0_climatology={"01-16": 3.45},
    )

    assert doc["region"]["id"] == "latur-2024"
    assert doc["referenceDate"] == "2024-01-16"
    assert len(doc["scenes"]) == 1
    assert len(doc["ponds"]) == 1
    assert doc["ponds"][0]["id"] == "P001"
    assert "generatedAt" in doc
    # Strict exclusion check: No backend countdown/flag fields
    assert "daysLeft" not in doc["ponds"][0]
    assert "dryBy" not in doc["ponds"][0]
    assert "flag" not in doc["ponds"][0]


def test_export_measurements_json(tmp_path: Path):
    doc = {"region": {"id": "test"}, "ponds": []}
    out_file = tmp_path / "measurements.json"

    export_measurements_json(doc, out_file)

    assert out_file.exists()
    saved_data = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved_data == doc
