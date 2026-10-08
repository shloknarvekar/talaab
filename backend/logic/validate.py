"""Check a pipeline measurements.json against docs/measurements-contract.md before it goes live.

validate_measurements(meas) -> {"errors": [...], "warnings": [...], "stats": {...}}
errors   = the backend would crash or compute nonsense: fix before uploading.
warnings = suspicious but usable (worth a look).
Pure, no I/O.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
POND_RE = re.compile(r"^P\d{3,4}$")


def _is_date(s) -> bool:
    if not isinstance(s, str) or not DATE_RE.match(s):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def validate_measurements(meas: dict, mode: str = "replay") -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    for key in ("region", "scenes", "ponds"):
        if key not in meas:
            errors.append(f"missing top-level '{key}'")
    if errors:
        return {"errors": errors, "warnings": warnings, "stats": {}}

    region = meas["region"]
    bbox = region.get("bbox")
    if not region.get("id"):
        errors.append("region.id is empty")
    if not (isinstance(bbox, list) and len(bbox) == 4 and bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        errors.append("region.bbox must be [minLon, minLat, maxLon, maxLat]")
        bbox = None

    # scenes
    scene_dates = []
    for i, s in enumerate(meas["scenes"]):
        if not _is_date(s.get("date")):
            errors.append(f"scenes[{i}].date is not YYYY-MM-DD: {s.get('date')!r}")
            continue
        if s.get("status") not in ("ok", "suspect"):
            errors.append(f"scenes[{i}] ({s['date']}).status must be 'ok' or 'suspect'")
        scene_dates.append(s["date"])
    if scene_dates != sorted(scene_dates):
        errors.append("scenes must be sorted oldest first")
    if len(set(scene_dates)) != len(scene_dates):
        errors.append("scenes contain duplicate dates")
    if len(scene_dates) < 3:
        errors.append(f"only {len(scene_dates)} scenes: need at least 3 passes to fit any trend")
    scene_set = set(scene_dates)

    # ponds
    ids = [p.get("id") for p in meas["ponds"]]
    if not meas["ponds"]:
        errors.append("no ponds")
    if len(set(ids)) != len(ids):
        errors.append("duplicate pond ids")
    valid_points = total_points = 0
    for p in meas["ponds"]:
        pid = p.get("id", "?")
        if not POND_RE.match(str(pid)):
            errors.append(f"pond id {pid!r} must look like P001")
        lat, lon = p.get("lat"), p.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            errors.append(f"{pid}: lat/lon must be numbers")
        elif bbox and not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            warnings.append(f"{pid}: centroid ({lat}, {lon}) is outside the region bbox (lat/lon swapped?)")
        ref = p.get("refAreaHa")
        if not isinstance(ref, (int, float)) or ref <= 0:
            errors.append(f"{pid}: refAreaHa must be a positive number of hectares")
            ref = None
        elif not 1 <= ref <= 200:
            warnings.append(f"{pid}: refAreaHa {ref} ha is outside the 1-200 ha pond range")
        hist = p.get("history") or []
        if not hist:
            errors.append(f"{pid}: empty history")
            continue
        dates = [h.get("date") for h in hist]
        if dates != sorted(dates):
            errors.append(f"{pid}: history must be sorted oldest first")
        unknown = [d for d in dates if d not in scene_set]
        if unknown:
            errors.append(f"{pid}: history dates not in scenes: {unknown[:3]}")
        missing = scene_set - set(dates)
        if missing:
            warnings.append(f"{pid}: no history entry for {len(missing)} scene(s), e.g. {sorted(missing)[0]}")
        for h in hist:
            total_points += 1
            a = h.get("areaHa")
            if not isinstance(a, (int, float)) or a < 0:
                errors.append(f"{pid} {h.get('date')}: areaHa must be a number >= 0")
                continue
            if not isinstance(h.get("valid"), bool):
                errors.append(f"{pid} {h.get('date')}: valid must be true/false")
            valid_points += bool(h.get("valid"))
            if ref and h.get("valid") and a > 2 * ref:
                warnings.append(f"{pid} {h['date']}: {a} ha is more than twice its reference area {ref} ha (cloud as water?)")
        if not any(h.get("valid") for h in hist):
            warnings.append(f"{pid}: no valid pass at all")
    refs = [p.get("refAreaHa") or 0 for p in meas["ponds"]]
    if refs != sorted(refs, reverse=True):
        warnings.append("ponds are not sorted by refAreaHa, largest first (P001 should be the biggest)")

    # weather
    et0 = meas.get("et0") or []
    if mode == "replay" and scene_dates:
        need_from = date.fromisoformat(scene_dates[0]) - timedelta(days=25)
        have = {x.get("date") for x in et0 if x.get("et0") is not None}
        span = (date.fromisoformat(scene_dates[-1]) - need_from).days + 1
        gaps = [d for d in (need_from + timedelta(days=i) for i in range(span)) if d.isoformat() not in have]
        if gaps:
            errors.append(f"et0 is missing {len(gaps)} day(s) between {need_from} and {scene_dates[-1]} (first gap {gaps[0]})")
        clim = meas.get("et0Climatology") or {}
        if len(clim) < 365:
            errors.append(f"et0Climatology has {len(clim)} days; need all 365/366 'MM-DD' keys for the heat expectation")
    for x in et0:
        v = x.get("et0")
        if v is not None and not 0 <= v <= 15:
            warnings.append(f"et0 {x.get('date')}: {v} mm/day looks wrong (expected 0-15)")
            break

    stats = {
        "ponds": len(meas["ponds"]),
        "scenes": len(scene_dates),
        "firstScene": scene_dates[0] if scene_dates else None,
        "lastScene": scene_dates[-1] if scene_dates else None,
        "suspectScenes": sum(1 for s in meas["scenes"] if s.get("status") == "suspect"),
        "validShare": round(valid_points / total_points, 3) if total_points else 0,
        "et0Days": len(et0),
    }
    return {"errors": errors, "warnings": warnings, "stats": stats}
