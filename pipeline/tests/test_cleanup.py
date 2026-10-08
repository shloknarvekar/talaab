"""Tests for pipeline/cleanup.py scene suspect detection and spike dropping module."""

from pipeline.cleanup import clean_spike_measurements, detect_suspect_scenes


def test_detect_suspect_scenes():
    scene_dates = ["2024-01-16", "2024-01-21", "2024-01-26"]
    # Total area jumps >40% on 2024-01-21 without rain
    total_area = {
        "2024-01-16": 100.0,
        "2024-01-21": 150.0,  # +50% jump
        "2024-01-26": 105.0,
    }
    precip = {
        "2024-01-16": 0.0,
        "2024-01-17": 0.0,
        "2024-01-18": 0.0,
        "2024-01-19": 0.0,
        "2024-01-20": 0.0,
        "2024-01-21": 0.0,  # Rain < 5mm
    }

    suspect = detect_suspect_scenes(scene_dates, total_area, precip)
    assert suspect == ["2024-01-21"]


def test_clean_spike_measurements():
    history = [
        {"date": "2024-01-16", "areaHa": 10.0, "valid": True},
        {"date": "2024-01-21", "areaHa": 18.0, "valid": True},  # Spike up (> 50%)
        {"date": "2024-01-26", "areaHa": 9.0, "valid": True},   # Spike down (< 75% of 18.0)
    ]
    # No rain
    precip = {"2024-01-17": 0.0, "2024-01-18": 0.0, "2024-01-19": 0.0, "2024-01-20": 0.0, "2024-01-21": 0.0}

    cleaned = clean_spike_measurements(history, precip)

    assert cleaned[0]["valid"] is True
    assert cleaned[1]["valid"] is False  # Spike cleaned (valid set to False)
    assert cleaned[2]["valid"] is True
