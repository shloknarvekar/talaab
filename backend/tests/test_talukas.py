"""Talukas: OSM boundaries, tagging ponds, the per-taluka summary, and how plans and alerts use it."""
import json
import math
from pathlib import Path

import pytest

from jobs.alerts import format_alert, new_alerts
from jobs.talukas import MAX_EDGE_KM, load_talukas, tag_ponds, taluka_of, talukas_for_region
from logic.plan import MAX_LIST_ITEMS, MAX_VILLAGE_ROWS, build_plan
from logic.talukas import summarise

ROOT = Path(__file__).resolve().parents[2]
LATUR = load_talukas("latur")


def _area_km2(geometry):
    total = 0.0
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for poly in polys:
        for k, ring in enumerate(poly):
            lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
            pts = [(math.radians(p[0]) * 6371.0 * math.cos(lat0), math.radians(p[1]) * 6371.0) for p in ring]
            a = 0.5 * abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1])))
            total += a if k == 0 else -a
    return total


def test_latur_has_its_ten_talukas_and_they_cover_the_district():
    names = sorted(t["name"] for t in LATUR)
    assert names == ["Ahmadpur", "Ausa", "Chakur", "Deoni", "Jalkot", "Latur", "Nilanga", "Renapur",
                     "Shirur-Anantpal", "Udgir"]
    assert all(t["nameMr"] for t in LATUR)  # Marathi names for the Marathi plan
    district = json.loads((ROOT / "pipeline" / "boundaries" / "latur-district.json").read_text(encoding="utf-8"))
    assert sum(_area_km2(t["geometry"]) for t in LATUR) == pytest.approx(_area_km2(district["geometry"]), rel=0.01)


@pytest.mark.parametrize("lat,lon,expected", [  # town nodes from OSM (backend/jobs/places/latur.json)
    (18.39823, 76.56259, "Latur"),
    (18.39213, 77.11961, "Udgir"),
    (18.70612, 76.93773, "Ahmadpur"),
    (18.12919, 76.74941, "Nilanga"),
    (18.25102, 76.50096, "Ausa"),
    (18.33673, 76.83961, "Shirur-Anantpal"),
])
def test_towns_fall_in_their_own_taluka(lat, lon, expected):
    assert taluka_of(lat, lon, LATUR)["name"] == expected


def test_far_outside_the_district_gets_no_taluka():
    assert taluka_of(19.88, 75.34, LATUR) is None  # Aurangabad, ~200 km away
    assert MAX_EDGE_KM <= 2.0


def test_tag_ponds_and_region_lookup():
    ponds = [{"id": "P001", "lat": 18.4088, "lon": 76.5604}, {"id": "P002", "lat": 19.88, "lon": 75.34}]
    assert tag_ponds(ponds, talukas_for_region("latur-district-2026")) == 1
    assert ponds[0]["taluka"] == "Latur" and ponds[0]["talukaMr"] == "लातूर" and "taluka" not in ponds[1]
    assert talukas_for_region("nowhere-2024") == ()


def pond(pid, taluka, status, likely=None, flag=None):
    return {"id": pid, "taluka": taluka, "talukaMr": {"Udgir": "उदगीर", "Ausa": "औसा"}.get(taluka), "status": status,
            "flag": flag, "dryBy": {"earliest": likely, "likely": likely, "latest": likely} if likely else None,
            "daysLeft": {"min": 5, "likely": 7, "max": 9} if likely else None, "place": f"near V{pid}",
            "areaNowHa": 1.0, "maxAreaHa": 4.0, "shrinkVsNeighbours": 2.5 if flag else 1.0, "lat": 18.4, "lon": 76.5}


def test_summary_counts_and_orders_most_urgent_first():
    ponds = [pond("P1", "Ausa", "ok"), pond("P2", "Udgir", "critical", "2026-10-20"), pond("P3", "Udgir", "dry", "2026-10-01"),
             pond("P4", "Udgir", "watch", "2026-11-30", flag="faster-than-sun"), pond("P5", "Ausa", "unknown"), pond("P6", None, "dry")]
    s = summarise(ponds)
    assert [g["name"] for g in s] == ["Udgir", "Ausa"]  # untagged P6 left out
    u = s[0]
    assert (u["ponds"], u["dry"], u["critical"], u["watch"], u["flagged"]) == (3, 1, 1, 1, 1)
    assert u["earliestLikelyDry"] == "2026-10-20"  # the dry pond's date doesn't count
    assert s[1]["unknown"] == 1 and s[1]["earliestLikelyDry"] is None and u["nameMr"] == "उदगीर"


def _doc(ponds):
    return {"region": {"id": "latur-district-2026", "name": "Latur district (live, 2026)"}, "asOf": "2026-10-09",
            "live": True, "sunShareMm": 200.0, "scenes": [], "ponds": ponds, "talukas": summarise(ponds)}


def test_plan_starts_with_a_taluka_table_and_names_the_taluka_of_each_pond():
    ponds = [pond("P001", "Udgir", "critical", "2026-10-20"), pond("P002", "Ausa", "ok")]
    md = build_plan(_doc(ponds), "en")["markdown"]
    assert md.index("## By taluka") < md.index("## By village")
    assert "| Udgir | 1 | 0 | 1 | 0 | 0 | 0 | 20 Oct 2026 |" in md
    assert "**P001** (near VP001, Udgir taluka)" in md
    mr = build_plan(_doc(ponds), "mr")["markdown"]
    assert "## तालुकानिहाय स्थिती" in mr and "| उदगीर |" in mr and "उदगीर तालुका" in mr


def test_district_scale_plan_groups_low_priority_ponds_by_taluka():
    n = max(MAX_LIST_ITEMS, MAX_VILLAGE_ROWS) + 1  # 31: more than both limits
    ponds = [pond(f"P{i:03d}", "Udgir" if i % 2 else "Ausa", "unknown") for i in range(1, n + 1)]
    out = build_plan(_doc(ponds), "en")
    section = out["markdown"].split("No recent clear satellite pass")[1].split("\n## ")[0]
    assert "- **Udgir** (16): P001, P003" in section and "- **Ausa** (15): P002" in section
    assert len(out["pondIds"]) == len(ponds)  # every pond still cited
    assert f"{n} more villages have only ok or not-yet-visible ponds" in out["markdown"]


def test_regions_without_talukas_are_unchanged():
    p = pond("P001", None, "critical", "2026-10-20")
    md = build_plan({**_doc([p]), "talukas": []}, "en")["markdown"]
    assert "By taluka" not in md and "**P001** (near VP001)" in md


def test_alert_email_names_the_taluka():
    snap = {"asOf": "2026-10-09", "ponds": [pond("P001", "Udgir", "critical", "2026-10-20")]}
    _, body = format_alert("Latur district (live, 2026)", "2026-10-09", new_alerts({}, snap), "x")
    assert "P001 (near VP001, Udgir taluka) turned CRITICAL" in body
