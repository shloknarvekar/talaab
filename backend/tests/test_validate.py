import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from synth_measurements import generate  # noqa: E402

from api import handler, store  # noqa: E402
from logic.validate import validate_measurements  # noqa: E402

GOOD = generate()


def test_synthetic_file_is_valid():
    r = validate_measurements(GOOD)
    assert r["errors"] == [] and r["stats"]["ponds"] == 14 and r["stats"]["scenes"] == 31


def test_catches_common_pipeline_mistakes():
    bad = copy.deepcopy(GOOD)
    bad["scenes"][3]["date"] = "2024/02/01"                  # wrong date format
    bad["ponds"][1]["id"] = "pond-2"                          # wrong id format
    bad["ponds"][2]["lat"], bad["ponds"][2]["lon"] = bad["ponds"][2]["lon"], bad["ponds"][2]["lat"]  # swapped
    bad["ponds"][4]["history"][5]["areaHa"] = -1              # negative area
    bad["ponds"][5]["history"][6]["valid"] = "yes"            # not a bool
    bad["et0"] = bad["et0"][:50]                              # weather gap
    r = validate_measurements(bad)
    text = " | ".join(r["errors"] + r["warnings"])
    assert "not YYYY-MM-DD" in text and "must look like P001" in text
    assert "outside the region bbox" in text and "areaHa must be a number >= 0" in text
    assert "valid must be true/false" in text and "et0 is missing" in text


def test_missing_top_level_and_live_mode_weather():
    assert validate_measurements({"region": {}})["errors"]
    live = {**copy.deepcopy(GOOD), "et0": [], "et0Climatology": {}}
    assert validate_measurements(live, mode="live")["errors"] == []      # live: job fetches weather
    assert any("et0" in e for e in validate_measurements(live, mode="replay")["errors"])


def test_regions_route_lists_only_published(tmp_path, monkeypatch):
    (tmp_path / "latur-2024-synthetic").mkdir()
    (tmp_path / "latur-2024-synthetic" / "index.json").write_text(json.dumps({"asOf": ["2024-02-05", "2024-06-14"]}))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store.clear_cache()
    r = handler.lambda_handler({"routeKey": "GET /regions"}, None)
    regions = json.loads(r["body"])["regions"]
    assert [x["id"] for x in regions] == ["latur-2024-synthetic"]
    assert regions[0]["first"] == "2024-02-05" and regions[0]["last"] == "2024-06-14" and regions[0]["synthetic"]
    store.clear_cache()
