"""AI plan flow with a fake model (no Bedrock calls, no AWS)."""
import json
from pathlib import Path

import pytest

from agent import plan_agent, worker
from api import plans, store
from logic.guard import invented_numbers

MOCK = json.loads((Path(__file__).resolve().parents[2] / "web" / "public" / "mock" / "ponds.json").read_text(encoding="utf-8"))

GOOD = """# Water-scarcity plan: Latur (2024 replay), as of 26 March 2024
The sun's share over 45 days: 239.2 mm.
## Already dry
- **P004**: 0.1 ha of 5.8 ha. Arrange tankers.
## Apr–Jun 2024
- **P003**: 8.6 ha of 33.3 ha, dry 5 April 2024 to 11 April 2024 (likely 8 April 2024).
## Inspect
- **P003** shrinks 2.33 times faster than neighbours."""

BAD = GOOD + "\nAbout 12000 people depend on P003 and need 140 tankers."


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    region = tmp_path / "latur-2024" / "asof"
    region.mkdir(parents=True)
    (region / "2024-03-26.json").write_text(json.dumps(MOCK), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store.clear_cache()
    yield tmp_path
    store.clear_cache()


def fake_runner(*replies):
    calls = []
    it = iter(replies)

    def run(prompt):
        calls.append(prompt)
        return next(it)

    run.calls = calls
    return run


def test_guard_accepts_data_numbers_and_rejects_invented():
    assert invented_numbers(GOOD, MOCK) == set()
    assert invented_numbers(BAD, MOCK) == {"12000", "140"}
    # known limit: 1-31 always pass so dates can be written out
    assert invented_numbers("3 ponds", MOCK) == set()
    assert invented_numbers("P003: ८.६ हे.", MOCK) == set()  # Devanagari digits normalised
    assert invented_numbers("41 ha of 33.30 ha", MOCK) == set()  # 41.0 / 33.3 formatting


def test_write_plan_passes_first_time():
    run = fake_runner(GOOD)
    out = plan_agent.write_plan(MOCK, "en", runner=run)
    assert out["source"] == "bedrock" and out["pondIds"] == ["P004", "P003"]
    assert len(run.calls) == 1 and "latur-2024" in run.calls[0] and "2024-03-26" in run.calls[0]


def test_write_plan_retries_once_then_accepts():
    run = fake_runner(BAD, GOOD)
    out = plan_agent.write_plan(MOCK, "en", runner=run)
    assert out["markdown"] == GOOD
    assert "12000" in run.calls[1] and "140" in run.calls[1]


def test_write_plan_rejects_twice():
    with pytest.raises(ValueError, match="number guard"):
        plan_agent.write_plan(MOCK, "en", runner=fake_runner(BAD, BAD))


def test_tools_only_expose_the_requested_snapshot():
    get_ponds, get_pond = plan_agent.make_tools(MOCK)
    full = get_ponds(region="latur-2024", as_of="2024-03-26")
    assert len(full["ponds"]) == 4 and "history" not in full["ponds"][0]
    assert "error" in get_ponds(region="latur-2024", as_of="2024-05-01")
    assert get_pond(pond_id="P003")["history"]
    assert "error" in get_pond(pond_id="P999")


def test_plan_flow_ai_off_returns_template():
    out = plans.get_plan(MOCK, "en")
    assert out["status"] == "template" and out["source"] == "template"


def test_plan_flow_generating_then_ready(monkeypatch):
    started = []
    monkeypatch.setenv("PLAN_AI", "on")
    monkeypatch.setenv("PLAN_WORKER", "talaab-plan-worker")
    monkeypatch.setattr(plans, "_start_worker", lambda *a: started.append(a))

    first = plans.get_plan(MOCK, "en")
    assert first["status"] == "generating" and first["source"] == "template"
    second = plans.get_plan(MOCK, "en")  # worker still running: no second Bedrock call
    assert second["status"] == "generating" and len(started) == 1

    monkeypatch.setattr(worker, "write_plan", lambda doc, lang: plan_agent.write_plan(doc, lang, runner=fake_runner(GOOD)))
    assert worker.lambda_handler({"region": "latur-2024", "asOf": "2024-03-26", "language": "en"}, None)["ok"]

    ready = plans.get_plan(MOCK, "en")
    assert ready["status"] == "ready" and ready["source"] == "bedrock" and ready["markdown"] == GOOD
    assert len(started) == 1


def test_plan_flow_failure_falls_back_with_reason(monkeypatch):
    monkeypatch.setenv("PLAN_AI", "on")
    monkeypatch.setenv("PLAN_WORKER", "talaab-plan-worker")
    monkeypatch.setattr(plans, "_start_worker", lambda *a: None)
    plans.get_plan(MOCK, "mr")

    def boom(doc, lang):
        raise RuntimeError("Operation not allowed")

    monkeypatch.setattr(worker, "write_plan", boom)
    assert not worker.lambda_handler({"region": "latur-2024", "asOf": "2024-03-26", "language": "mr"}, None)["ok"]
    out = plans.get_plan(MOCK, "mr")
    assert out["status"] == "template" and "Operation not allowed" in out["aiError"]
