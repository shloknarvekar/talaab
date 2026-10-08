import json
from pathlib import Path

from jobs import places as places_mod
from jobs.places import distance_km, name_ponds, nearest
from logic.plan import build_plan

PLACES = (
    {"name": "Harangul", "nameMr": "हरंगुळ", "type": "village", "lat": 18.43, "lon": 76.52},
    {"name": "Khadgaon", "nameMr": None, "type": "village", "lat": 18.38, "lon": 76.60},
)
MOCK = json.loads((Path(__file__).resolve().parents[2] / "web" / "public" / "mock" / "ponds.json").read_text(encoding="utf-8"))


def test_distance_is_sane():
    assert distance_km(18.43, 76.52, 18.43, 76.52) == 0
    assert 1.0 < distance_km(18.43, 76.52, 18.44, 76.52) < 1.2  # ~1.1 km per 0.01 deg latitude


def test_nearest_within_5_km_only():
    assert nearest(18.431, 76.521, PLACES)["name"] == "Harangul"
    assert nearest(18.381, 76.601, PLACES)["name"] == "Khadgaon"
    assert nearest(18.90, 76.90, PLACES) is None  # ~60 km away: no fake name


def test_name_ponds_keeps_pipeline_names_and_adds_marathi():
    ponds = [{"id": "P001", "lat": 18.431, "lon": 76.521, "place": ""},
             {"id": "P002", "lat": 18.381, "lon": 76.601},
             {"id": "P003", "lat": 18.431, "lon": 76.521, "place": "near Talav Wadi"},
             {"id": "P004", "lat": 18.90, "lon": 76.90}]
    assert name_ponds(ponds, PLACES) == 2
    assert ponds[0]["place"] == "near Harangul" and ponds[0]["placeMr"] == "हरंगुळ"
    assert ponds[1]["place"] == "near Khadgaon" and "placeMr" not in ponds[1]
    assert ponds[2]["place"] == "near Talav Wadi"  # pipeline's own name kept
    assert not ponds[3].get("place")


def test_marathi_plan_uses_marathi_village_name():
    doc = json.loads(json.dumps(MOCK))
    doc["ponds"][0]["placeMr"] = "हरंगुळ"
    mr = build_plan(doc, "mr")["markdown"]
    assert f"**{doc['ponds'][0]['id']}** (हरंगुळ जवळ)" in mr and "| हरंगुळ |" in mr
    en = build_plan(doc, "en")["markdown"]
    assert "हरंगुळ" not in en  # English plan keeps the English name
    assert "OpenStreetMap" in en


def test_missing_places_file_means_no_names(monkeypatch, tmp_path):
    monkeypatch.setattr(places_mod, "PLACES_DIR", tmp_path)
    places_mod.load_places.cache_clear()
    assert places_mod.places_for_region("pune-2024") == ()
    places_mod.load_places.cache_clear()
