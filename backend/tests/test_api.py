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


def test_large_responses_are_gzipped_for_clients_that_accept_it():
    import base64
    import gzip
    event = {"routeKey": "GET /ponds", "queryStringParameters": {"region": "latur-2024"}, "headers": {"Accept-Encoding": "gzip, br"}}
    r = handler.lambda_handler(event, None)
    assert r["isBase64Encoded"] and r["headers"]["content-encoding"] == "gzip" and r["headers"]["vary"] == "accept-encoding"
    plain = handler.lambda_handler({**event, "headers": {}}, None)
    assert "isBase64Encoded" not in plain  # no Accept-Encoding: plain JSON, as before
    assert json.loads(gzip.decompress(base64.b64decode(r["body"]))) == json.loads(plain["body"])
    small = handler.lambda_handler({**event, "routeKey": "GET /nope"}, None)  # tiny error bodies stay plain
    assert "isBase64Encoded" not in small


def test_imagery_route_serves_index_and_refuses_anything_else(data_dir):
    idx = {"region": "latur-2024", "credit": "Contains modified Copernicus Sentinel data", "ponds": {"P001": {"dates": ["2024-01-16"]}}}
    (data_dir / "latur-2024" / "imagery").mkdir()
    (data_dir / "latur-2024" / "imagery" / "index.json").write_text(json.dumps(idx), encoding="utf-8")

    def get(path):
        r = handler.lambda_handler({"routeKey": "GET /imagery/{proxy+}", "pathParameters": {"proxy": path}}, None)
        return r["statusCode"], r

    status, r = get("latur-2024/index.json")
    assert status == 200 and json.loads(r["body"]) == idx
    for bad in ["latur-2024/../secret.json", "../data/x.json", "latur-2024/measurements.json", "latur-2024/P001/../../a.jpg",
                "latur-2024/P001/2024-01-16.png", "LATUR/index.json", ""]:
        assert get(bad)[0] == 404, bad
    assert get("latur-2024/outlines.geojson")[0] == 404          # not published yet
    assert get("latur-2024/P001/2024-01-16.jpg")[0] == 404       # thumbnails only via S3 links (no DATA_BUCKET here)


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


def test_division_summary_and_plan(data_dir):
    from tests.test_division import doc as division_doc
    d = division_doc({"Jalna": "जालना", "Beed": "बीड"})
    base = data_dir / "marathwada-2026"
    (base / "division").mkdir(parents=True)
    (base / "division.json").write_text(json.dumps(d), encoding="utf-8")
    (base / "division" / "2026-10-05.json").write_text(json.dumps({**d, "asOf": "2026-10-05"}), encoding="utf-8")
    (base / "division" / "2026-10-10.json").write_text(json.dumps(d), encoding="utf-8")

    status, latest = call("GET /division")
    assert status == 200 and latest["asOf"] == "2026-10-10" and latest["totals"]["ponds"] == 7
    assert call("GET /division", {"asOf": "2026-10-07"})[1]["asOf"] == "2026-10-05"  # never the future
    assert call("GET /division", {"asOf": "2026-10-01"})[0] == 404
    assert call("GET /division", {"division": "vidarbha-2026"})[0] == 404

    regions = call("GET /regions")[1]
    assert regions["divisions"][0]["id"] == "marathwada-2026" and regions["divisions"][0]["dates"] == ["2026-10-05", "2026-10-10"]
    assert "latur-district-2026" in regions["divisions"][0]["members"] and regions["divisions"][0]["last"] == "2026-10-10"

    status, plan = call("POST /plan", body={"region": "marathwada-2026", "language": "mr"})
    assert status == 200 and plan["status"] == "template" and "जिल्हानिहाय स्थिती" in plan["markdown"]
    status, plan = call("POST /plan", body={"region": "marathwada-2026", "asOf": "2026-10-07", "language": "en"})
    assert status == 200 and plan["asOf"] == "2026-10-05" and "## By district" in plan["markdown"]


def test_division_outlines_cover_every_member_district():
    from jobs.regions import division_members
    status, geo = call("GET /division/outlines")
    assert status == 200 and geo["type"] == "FeatureCollection" and "OpenStreetMap" in geo["credit"]
    assert sorted(f["properties"]["region"] for f in geo["features"]) == sorted(division_members("marathwada-2026"))
    for f in geo["features"]:
        assert f["geometry"]["type"] in ("Polygon", "MultiPolygon") and f["properties"]["nameMr"]
        rings = f["geometry"]["coordinates"] if f["geometry"]["type"] == "Polygon" else [r for p in f["geometry"]["coordinates"] for r in p]
        assert all(r[0] == r[-1] and len(r) >= 4 for r in rings)
        assert all(72 < x < 81 and 15 < y < 22 for r in rings for x, y in r)  # inside Maharashtra
    r = handler.lambda_handler({"routeKey": "GET /division/outlines", "queryStringParameters": None}, None)
    assert r["headers"]["cache-control"] == "public, max-age=86400"
    assert call("GET /division/outlines", {"division": "vidarbha-2026"})[0] == 404
    assert call("GET /division/outlines", {"division": "../x"})[0] == 404
