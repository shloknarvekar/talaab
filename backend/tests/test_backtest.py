import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from synth_measurements import generate  # noqa: E402

from api import handler, store  # noqa: E402
from logic.backtest import actual_dry_window, backtest  # noqa: E402

MEAS = generate()


def h(*pairs):
    return [{"date": d, "areaHa": a, "valid": v} for d, a, v in pairs]


def test_dry_window_basic_and_noise():
    hist = h(("2024-01-01", 10, True), ("2024-01-06", 5, True), ("2024-01-11", 0.3, True), ("2024-01-16", 0.2, True))
    assert actual_dry_window(hist) == (date(2024, 1, 6), date(2024, 1, 11))
    # a single low reading that recovers is not "dried"
    blip = h(("2024-01-01", 10, True), ("2024-01-06", 0.2, True), ("2024-01-11", 6, True))
    assert actual_dry_window(blip) is None
    # invalid passes are ignored when finding the last wet pass
    gap = h(("2024-01-01", 10, True), ("2024-01-06", 9, False), ("2024-01-11", 0.1, True))
    assert actual_dry_window(gap) == (date(2024, 1, 1), date(2024, 1, 11))


def test_backtest_scores_are_sane_on_synthetic():
    r = backtest(MEAS)
    s = r["summary"]
    assert r["synthetic"] is True and r["evaluated"]["pondsThatDried"] == 7
    assert 0 <= s["rangeHitRate"] <= 1 and s["rangeHits"] > 0
    assert s["criticalRecall"] >= 0.8 and s["medianLeadDays"] >= 14
    assert "noHeatAdjustment" in r["variants"]
    dried = {p["id"] for p in r["ponds"] if p["actualDry"]}
    assert "P003" in dried and "P014" not in dried  # pumped pond dried; spring-fed did not


def test_heat_variant_is_a_real_comparison():
    """The no-heat variant runs the same scoring with ET0 scaling off (future-blindness of each
    prediction is tested on the snapshot builder in test_snapshot.py)."""
    r = backtest(MEAS)
    assert r["variants"]["noHeatAdjustment"] != r["summary"]
    assert r["variants"]["noHeatAdjustment"]["shouldHaveWarned"] == r["summary"]["shouldHaveWarned"]  # same truth


def test_backtest_route(tmp_path, monkeypatch):
    (tmp_path / "latur-2024-synthetic").mkdir()
    (tmp_path / "latur-2024-synthetic" / "backtest.json").write_text(json.dumps(backtest(MEAS)), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store.clear_cache()
    r = handler.lambda_handler({"routeKey": "GET /backtest", "queryStringParameters": {"region": "latur-2024-synthetic"}}, None)
    assert r["statusCode"] == 200 and json.loads(r["body"])["summary"]["rangeHits"] > 0
    r = handler.lambda_handler({"routeKey": "GET /backtest", "queryStringParameters": {"region": "latur-2024"}}, None)
    assert r["statusCode"] == 404
    store.clear_cache()
