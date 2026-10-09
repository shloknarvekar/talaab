"""Tests for pipeline/cleanup.py: suspect passes, spikes and dips, pond existence and plausibility."""

from pipeline.cleanup import (
    apply_quality_rules,
    assess_pond,
    clean_spike_measurements,
    detect_suspect_scenes,
    invalidate_suspect_passes,
)

DRY = {f"2024-0{m}-{d:02d}": 0.0 for m in (1, 2, 3, 4) for d in range(1, 29)}  # no rain


def hist(*vals, start_day=1, step=5, valid=None):
    out = []
    for i, v in enumerate(vals):
        day = start_day + i * step
        m, d = 1 + (day - 1) // 28, 1 + (day - 1) % 28
        out.append({"date": f"2024-{m:02d}-{d:02d}", "areaHa": v, "valid": True if valid is None else valid[i]})
    return out


def test_detect_suspect_scenes():
    scene_dates = ["2024-01-16", "2024-01-21", "2024-01-26"]
    total_area = {"2024-01-16": 100.0, "2024-01-21": 150.0, "2024-01-26": 105.0}  # +50% jump
    precip = {"2024-01-17": 0.0, "2024-01-21": 0.0}
    assert detect_suspect_scenes(scene_dates, total_area, precip) == ["2024-01-21"]


def test_region_wide_dip_is_suspect_but_its_good_neighbours_are_not():
    dates = ["2024-01-01", "2024-01-06", "2024-01-11", "2024-01-16", "2024-01-21"]
    totals = {"2024-01-01": 160.0, "2024-01-06": 25.0, "2024-01-11": 150.0, "2024-01-16": 158.0, "2024-01-21": 150.0}
    # the broken 01-06 pass is caught; 01-11 must NOT be blamed for "jumping back up"
    assert detect_suspect_scenes(dates, totals, DRY) == ["2024-01-06"]


def test_end_of_series_fall_and_unjudgeable_rise_are_not_suspect():
    dates = ["2024-05-01", "2024-05-06", "2024-05-30"]
    assert detect_suspect_scenes(dates, {"2024-05-01": 100.0, "2024-05-06": 95.0, "2024-05-30": 40.0}, DRY) == []
    # no rain data (live post-monsoon): a rise cannot be judged
    rise = {"2026-09-27": 100.0, "2026-10-02": 160.0, "2026-10-07": 100.0}
    assert detect_suspect_scenes(list(rise), rise, {}) == []


def _areas(dates, ponds_by_date):
    """{date: {pond: area}} -> (areas_by_date, plain totals) for the same readings."""
    areas = {d: dict(ponds_by_date.get(d, {})) for d in dates}
    return areas, {d: sum(v.values()) for d, v in areas.items()}


def test_partly_cloudy_pass_is_not_suspect_when_compared_like_for_like():
    # 10 ponds of 10 ha, slowly shrinking. On 01-11 clouds hide 7 of them: the plain total falls 70%,
    # but the 3 ponds that WERE measured lost nothing unusual. That pass must stay usable.
    dates = ["2024-01-01", "2024-01-06", "2024-01-11", "2024-01-16", "2024-01-21"]
    full = {d: {f"P{k}": 10.0 - i * 0.2 for k in range(10)} for i, d in enumerate(dates)}
    full["2024-01-11"] = {k: v for k, v in full["2024-01-11"].items() if k in ("P0", "P1", "P2")}
    areas, totals = _areas(dates, full)
    assert detect_suspect_scenes(dates, totals, DRY) == ["2024-01-11"]          # old rule: a false alarm
    assert detect_suspect_scenes(dates, totals, DRY, areas_by_date=areas) == []  # paired: correct


def test_paired_rule_still_catches_a_broken_pass():
    # every pond reads ~15% of its area on 01-06 (bad pass), back to normal on 01-11
    dates = ["2024-01-01", "2024-01-06", "2024-01-11", "2024-01-16", "2024-01-21"]
    ponds = {d: {f"P{k}": 10.0 for k in range(6)} for d in dates}
    ponds["2024-01-06"] = {f"P{k}": 1.5 for k in range(6)}
    areas, totals = _areas(dates, ponds)
    assert detect_suspect_scenes(dates, totals, DRY, areas_by_date=areas) == ["2024-01-06"]


def test_pairs_with_too_few_shared_ponds_are_not_judged():
    dates = ["2024-01-01", "2024-01-06", "2024-01-11"]
    ponds = {"2024-01-01": {"A": 10.0, "B": 10.0, "C": 10.0}, "2024-01-06": {"A": 1.0, "Z": 1.0},
             "2024-01-11": {"A": 10.0, "B": 10.0, "C": 10.0}}
    areas, totals = _areas(dates, ponds)
    assert detect_suspect_scenes(dates, totals, DRY, areas_by_date=areas) == []  # only 1 pond in common


def test_quality_rules_compare_passes_like_for_like():
    # apply_quality_rules passes per-pond readings, so a partly cloudy pass keeps its good readings
    dates = ["2024-01-01", "2024-01-06", "2024-01-11", "2024-01-16", "2024-01-21"]
    ponds = [{"id": f"P{k:03d}", "lat": 18.4, "lon": 76.5 + k / 100, "refAreaHa": 10.0,
              "history": [{"date": d, "areaHa": 10.0 - i * 0.2, "valid": not (d == "2024-01-11" and k >= 3)}
                          for i, d in enumerate(dates)]} for k in range(10)]
    scenes = [{"date": d, "id": d, "status": "ok"} for d in dates]
    out_scenes, kept, _, report = apply_quality_rules(scenes, ponds, DRY, "2024-01-01")
    assert report["suspectScenes"] == [] and all(s["status"] == "ok" for s in out_scenes)
    assert sum(h["valid"] for p in kept for h in p["history"] if h["date"] == "2024-01-11") == 3


def test_rain_explains_a_rise():
    dates = ["2024-06-01", "2024-06-06", "2024-06-11"]
    totals = {"2024-06-01": 100.0, "2024-06-06": 170.0, "2024-06-11": 175.0}
    assert detect_suspect_scenes(dates, totals, {"2024-06-04": 40.0}) == []


def test_suspect_pass_readings_are_invalidated():
    h = hist(10, 9, 8)
    out = invalidate_suspect_passes(h, [h[1]["date"]])
    assert [x["valid"] for x in out] == [True, False, True] and h[1]["valid"] is True  # no mutation


def test_clean_spike_measurements():
    history = [
        {"date": "2024-01-16", "areaHa": 10.0, "valid": True},
        {"date": "2024-01-21", "areaHa": 18.0, "valid": True},  # spike up (> 50%)
        {"date": "2024-01-26", "areaHa": 9.0, "valid": True},   # back down (< 75% of 18.0)
    ]
    precip = {"2024-01-17": 0.0, "2024-01-21": 0.0}
    cleaned = clean_spike_measurements(history, precip)
    assert [h["valid"] for h in cleaned] == [True, False, True]


def test_single_pass_dip_is_dropped_but_real_drying_is_kept():
    assert [h["valid"] for h in clean_spike_measurements(hist(7.8, 0.9, 6.9, 6.6), DRY)] == [True, False, True, True]
    drying = clean_spike_measurements(hist(1.4, 1.1, 0.6, 0.0, 0.0), DRY)
    assert all(h["valid"] for h in drying)
    tiny = clean_spike_measurements(hist(0.5, 0.0, 0.1, 0.2), DRY)  # below the 0.3 ha noise floor
    assert all(h["valid"] for h in tiny)


def test_pond_seen_only_on_reference_date_is_excluded():
    h = hist(0.1, 0.0, 0.2, 5.7, 0.1, 0.0)  # reference date = 4th pass (2024-01-16)
    keep, reason = assess_pond(h, "2024-01-16", 5.7, DRY)
    assert not keep and "mis-detection" in reason


def test_real_pond_that_dries_fast_is_kept():
    h = hist(3.4, 3.1, 2.9, 2.9, 2.1, 1.4, 1.1, 0.6, 0.0, 0.0)
    assert assess_pond(h, "2024-01-16", 2.9, DRY) == (True, None)


def test_unexplained_dry_season_rise_is_excluded_unless_rain():
    h = hist(37.0, 37.0, 37.1, 37.1, 41.0, 26.4, 6.9, 12.1, 16.4, 26.0, 41.5, 33.8)
    keep, reason = assess_pond(h, "2024-01-16", 37.1, DRY)
    assert not keep and "unexplained rise" in reason
    wet = {d: 15.0 for d in DRY}
    assert assess_pond(h, "2024-01-16", 37.1, wet)[0]           # rain could explain it
    assert assess_pond(h, "2024-01-16", 37.1, {})[0]            # no rain data: not judged


def test_apply_quality_rules_end_to_end_renumbers_by_area():
    dates = [f"2024-01-{d:02d}" for d in (1, 6, 11, 16, 21, 26)]
    scenes = [{"date": d, "id": f"S{d}", "status": "ok"} for d in dates]

    def pond(pid, ref, vals):
        return {"id": pid, "lat": 18.4, "lon": 76.5, "place": "", "refAreaHa": ref,
                "history": [{"date": d, "areaHa": v, "valid": True} for d, v in zip(dates, vals)]}

    ponds = [
        pond("P001", 30.0, [30, 2, 30, 30, 29, 29]),     # real; 01-06 broken everywhere
        pond("P002", 20.0, [20, 1, 20, 20, 19, 19]),     # real
        pond("P003", 5.0, [0, 0, 0.1, 5.0, 0.1, 0.0]),  # seen only on the reference date
    ]
    scenes_out, kept, excluded, report = apply_quality_rules(scenes, ponds, DRY, "2024-01-16")
    assert report["suspectScenes"] == ["2024-01-06"]
    assert [s["status"] for s in scenes_out].count("suspect") == 1
    assert [p["id"] for p in kept] == ["P001", "P002"] and [e["id"] for e in excluded] == ["P003"]
    assert all(not h["valid"] for p in kept for h in p["history"] if h["date"] == "2024-01-06")
