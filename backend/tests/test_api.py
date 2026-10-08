import json
from pathlib import Path

import pytest

from api import handler, store

MOCK = Path(__file__).resolve().parents[2] / "web" / "public" / "mock" / "ponds.json"


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    doc = json.loads(MOCK.read_text(encoding="utf-8"))
    region = tmp_path / "latur-2024"
    (region / "asof").mkdir(parents=True)
    (region / "asof" / "2024-03-26.json").write_text(json.dumps(doc), encoding="utf-8")
    early = {**doc, "asOf": "2024-02-25"}
    (region / "asof" / "2024-02-25.json").write_text(json.dumps(early), encoding="utf-8")
    (region / "index.json").write_text(json.dumps({"asOf": ["2024-02-25", "2024-03-26"]}), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store.clear_cache()
    yield tmp_path
    store.clear_cache()


def call(route, query=None, path=None, body=None):
    event = {"routeKey": route, "queryStringParameters": query, "pathParameters": path}
    if body is not None:
        event["body"] = json.dumps(body)
    r = handler.lambda_handler(event, None)
    return r["statusCode"], json.loads(r["body"])


def test_get_ponds_latest_and_as_of_resolution():
    status, doc = call("GET /ponds", {"region": "latur-2024"})
    assert status == 200 and doc["asOf"] == "2024-03-26" and len(doc["ponds"]) == 4
    # a date between snapshots resolves to the earlier one (never shows the future)
    status, doc = call("GET /ponds", {"region": "latur-2024", "asOf": "2024-03-10"})
    assert status == 200 and doc["asOf"] == "2024-02-25"


def test_default_region_and_bad_params():
    assert call("GET /ponds")[0] == 200
    assert call("GET /ponds", {"asOf": "26-03-2024"})[0] == 400
    assert call("GET /ponds", {"region": "../etc"})[0] == 400
    assert call("GET /ponds", {"asOf": "2023-12-31"})[0] == 404  # before first snapshot
    assert call("GET /ponds", {"region": "pune-2024"})[0] == 404


def test_get_single_pond():
    status, pond = call("GET /ponds/{id}", {"asOf": "2024-03-26"}, {"id": "P003"})
    assert status == 200 and pond["id"] == "P003" and pond["flag"] == "faster-than-sun"
    assert pond["asOf"] == "2024-03-26" and pond["region"] == "latur-2024"
    assert call("GET /ponds/{id}", None, {"id": "P999"})[0] == 404
    assert call("GET /ponds/{id}", None, {"id": "drop table"})[0] == 400


def test_plan_endpoint_en_and_mr():
    status, plan = call("POST /plan", body={"region": "latur-2024", "asOf": "2024-03-26", "language": "en"})
    assert status == 200 and plan["source"] == "template"
    assert set(plan["pondIds"]) == {"P001", "P002", "P003", "P004"}
    status, mr = call("POST /plan", body={"language": "mr"})
    assert status == 200 and "पाणीटंचाई" in mr["markdown"]
    assert call("POST /plan", body={"language": "fr"})[0] == 400
    r = handler.lambda_handler({"routeKey": "POST /plan", "body": "not json"}, None)
    assert r["statusCode"] == 400


def test_unknown_route():
    assert call("DELETE /ponds")[0] == 404
