"""Local AI briefing (agent/briefing.py, agent/llm_worker.py, api/plans.py local mode) with a fake model: no llama.cpp, no AWS."""
import json
from pathlib import Path

import pytest

from agent import briefing, llm_worker
from agent.briefing import (HEDGE, check_sentence, fix_names, groups_for_division, groups_for_snapshot, with_briefing,
                            write_briefing)
from api import plans, store

MOCK = json.loads((Path(__file__).resolve().parents[2] / "web" / "public" / "mock" / "ponds.json").read_text(encoding="utf-8"))

GOOD = {
    "situation": "As of 26 Mar 2024, Latur (2024 replay) has 1 dry and 1 critical pond out of 4, with 1 on watch.",
    "dry": "Pond P004 near Village D (mock) is already dry, with 0.1 of its 5.8 ha left, so its users need another water source now.",
    "critical": "Plan tankers or restrict use before pond P003 near Village C (mock) runs dry between 5 Apr 2024 and 11 Apr 2024.",
    "inspect": "Inspect pond P003 near Village C (mock): it is shrinking 2.33 times faster than its neighbours under the same sun.",
}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    (tmp_path / "latur-2024" / "asof").mkdir(parents=True)
    (tmp_path / "latur-2024" / "asof" / "2024-03-26.json").write_text(json.dumps(MOCK), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store.clear_cache()
    yield tmp_path
    store.clear_cache()


def fake(replies: dict):
    """A fake model: answers by the kind of sentence the prompt asks for (the instruction is the prompt's last line)."""
    calls = []

    def gen(prompt, temperature, seed):
        kind = next(k for k, text in briefing.INSTRUCTIONS.items() if prompt.rstrip().endswith(
            f"{text}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>"))
        calls.append((kind, temperature))
        reply = replies.get(kind, "")
        return reply.pop(0) if isinstance(reply, list) else reply

    gen.calls = calls
    return gen


def test_groups_give_each_sentence_only_its_own_facts():
    groups = dict(groups_for_snapshot(MOCK))
    assert list(groups) == ["situation", "dry", "critical", "inspect"]  # no talukas in the mock: no "where"
    assert groups["situation"]["asOf"] == "26 Mar 2024" and groups["situation"]["dry"] == 1
    assert groups["dry"]["dryPonds"] == [{"id": "P004", "location": "near Village D (mock)", "waterNowHa": 0.1, "fullHa": 5.8}]
    assert groups["critical"]["criticalPonds"] == [{"id": "P003", "location": "near Village C (mock)",
                                                    "likelyDry": "between 5 Apr 2024 and 11 Apr 2024"}]
    assert groups["inspect"]["pondsToInspect"] == [{"id": "P003", "location": "near Village C (mock)", "timesFasterThanNeighbours": 2.33}]
    assert "likelyDry" not in json.dumps(groups["inspect"])  # extra facts invite the model to mix them in


def test_division_groups_carry_the_change_as_plain_words():
    from tests.test_division import doc
    div = doc()
    div["change"] = {"since": "2026-10-05", "districts": 2, "dry": 1, "critical": -2, "watch": 0, "unknown": -9, "flagged": 3}
    groups = dict(groups_for_division(div))
    assert groups["change"] == {"area": "Marathwada (live, 2026)", "asOf": "10 Oct 2026", "since": "5 Oct 2026", "moreDry": 1,
                                "fewerCritical": 2, "moreFlagged": 3, "hiddenPondsNowForecastable": 9}
    assert groups["where"]["districts"][0]["district"] == "Jalna"
    assert groups["dry"]["dryPonds"][0]["location"] == "near VP002, Jafferabad taluka, Jalna district"


def test_checks_reject_what_a_small_model_gets_wrong():
    facts = dict(groups_for_snapshot(MOCK))
    assert check_sentence("critical", GOOD["critical"], facts["critical"]) == []
    assert any("numbers" in p for p in check_sentence("critical", GOOD["critical"].replace("11 Apr", "19 Apr"), facts["critical"]))
    assert any("numbers" in p for p in check_sentence("critical", GOOD["critical"].replace("before", "with 11 tankers before"),
                                                      facts["critical"]))  # a date's day number is not a free number
    assert any("pond ids" in p for p in check_sentence("dry", GOOD["dry"].replace("P004", "P001"), facts["dry"]))
    assert "names no pond" in check_sentence("critical", "Plan tankers or restrict use before the ponds run dry.", facts["critical"])
    assert "no action" in check_sentence("critical", "Pond P003 near Village C (mock) runs dry between 5 Apr 2024 and 11 Apr 2024.", facts["critical"])
    assert "unfinished sentence" in check_sentence("critical", GOOD["critical"][:-30], facts["critical"])
    pumping = "Inspect pond P003 near Village C (mock): it is shrinking 2.33 times faster because of illegal pumping."
    assert "states pumping as fact" in check_sentence("inspect", pumping, facts["inspect"])
    assert any("names not in" in p for p in check_sentence("dry", GOOD["dry"].replace("Village D", "Shivpur"), facts["dry"]))
    assert "not English" in check_sentence("situation", GOOD["situation"] + " सूर्य", facts["situation"])
    where = {"area": "Latur district (live, 2026)", "talukas": [{"taluka": "Udgir", "dry": 0, "critical": 3}, {"taluka": "Ahmadpur", "dry": 0, "critical": 2}]}
    assert check_sentence("where", "Act first in Udgir taluka, with 3 critical ponds, then in Ahmadpur taluka with 2 critical ponds.", where) == []
    assert any("does not start with Udgir" in p for p in check_sentence(
        "where", "Act first in Ahmadpur taluka with 2 critical ponds, then in Udgir taluka with 3 critical ponds.", where))
    assert any("not a district" in p for p in check_sentence("where", "Act first in Udgir district, with 3 critical ponds.", where))


def test_one_letter_misspellings_are_fixed_only_when_unambiguous():
    facts = {"talukas": [{"taluka": "Udgir"}, {"taluka": "Ahmadpur"}]}
    assert fix_names("Act first in Udgar taluka.", facts) == "Act first in Udgir taluka."
    assert fix_names("Act first in Udgirpur taluka.", facts) == "Act first in Udgirpur taluka."  # too far: left to the checks
    assert fix_names("Act in Bera.", {"talukas": [{"taluka": "Berd"}, {"taluka": "Bern"}]}) == "Act in Bera."  # two candidates


def test_write_briefing_resamples_drops_bad_bullets_and_hedges_pumping():
    gen = fake({**GOOD, "dry": ["Pond P004 is dry with 12 ha left, use 40 tankers.", "Still 99 ha.", "Nope 7."]})
    text, log = write_briefing(groups_for_snapshot(MOCK), gen)
    assert [k for k, _ in gen.calls].count("dry") == 3 and len(log["dry"]) == 3  # three samples, all rejected
    assert "P004" not in text and text.count("\n") == 2                           # dry bullet left out, 3 bullets
    assert text.endswith(HEDGE)                                                    # caveat added in fixed wording
    assert [t for k, t in gen.calls if k == "dry"] == [0.4, 0.2, 0.0]
    with pytest.raises(ValueError, match="only 1"):
        write_briefing(groups_for_snapshot(MOCK), fake({"situation": GOOD["situation"]}))


def test_briefing_sits_under_the_title_and_the_plan_is_unchanged():
    md = with_briefing("# Plan title\n\nBody line", "- one\n- two")
    assert md.startswith("# Plan title\n\n## Briefing\n\n- one\n- two\n\n_AI draft") and md.endswith("---\n\nBody line")


def test_worker_writes_a_cached_plan_or_a_failed_marker(data_dir):
    plan = llm_worker.write_plan("latur-2024", "2024-03-26", "en", gen=fake(GOOD))
    assert plan["source"] == "local-ai" and "## Briefing" in plan["markdown"] and "Qwen3" in plan["model"]
    assert set(plan["pondIds"]) == {"P001", "P002", "P003", "P004"}  # the template plan's citations
    saved = json.loads((data_dir / "latur-2024" / "plans" / "2024-03-26-en.json").read_text(encoding="utf-8"))
    assert saved["briefing"] == plan["briefing"]
    r = llm_worker._one("latur-2024", "2024-03-26", "en", gen=fake({}))
    assert r["ok"] is False and "briefing rejected" in r["reason"]
    status = json.loads((data_dir / "latur-2024" / "plans" / "2024-03-26-en.status.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed"


def test_jobs_skip_cached_plans_and_chain_before_the_time_limit(data_dir, monkeypatch):
    llm_worker.write_plan("latur-2024", "2024-03-26", "en", gen=fake(GOOD))
    assert llm_worker.run_jobs([{"region": "latur-2024", "asOf": "2024-03-26"}], gen=fake({})) == []  # cached: skipped
    chained = []
    monkeypatch.setattr(llm_worker, "CHAIN_AFTER_SECONDS", -1)
    ctx = type("Ctx", (), {"function_name": "talaab-plan-llm"})()
    jobs = [{"region": "latur-2024", "asOf": "2024-02-25"}]
    assert llm_worker.run_jobs(jobs, ctx, gen=fake({}), invoke=lambda name, payload: chained.append((name, payload))) == []
    assert chained == [("talaab-plan-llm", {"jobs": jobs})]


def test_plan_flow_local_mode_english_only_one_writer_at_a_time(monkeypatch):
    monkeypatch.setenv("PLAN_AI", "local")
    monkeypatch.setenv("PLAN_WORKER", "talaab-plan-llm")
    started = []
    monkeypatch.setattr(plans, "_start_worker", lambda *a: started.append(a))
    other = {**MOCK, "region": {**MOCK["region"], "id": "latur-district-2024"}}
    for doc in (MOCK, other):
        rid = doc["region"]["id"]
        (data_dir_path(rid)).mkdir(parents=True, exist_ok=True)
        (data_dir_path(rid).parent / "index.json").write_text(json.dumps({"asOf": ["2024-02-25", "2024-03-26"]}), encoding="utf-8")

    assert plans.get_plan(MOCK, "mr")["status"] == "template" and started == []      # Marathi: template only
    old = plans.get_plan({**MOCK, "asOf": "2024-02-25"}, "en")                          # not the latest data
    assert old["status"] == "template" and "latest" in old["aiNote"] and started == []
    assert plans.get_plan(MOCK, "en")["status"] == "generating" and len(started) == 1
    assert plans.get_plan(MOCK, "en")["status"] == "generating" and len(started) == 1  # same plan: not started twice
    busy = plans.get_plan(other, "en")                                                  # another plan while one runs
    assert busy["status"] == "template" and "busy" in busy["aiNote"] and len(started) == 1
    plans.release_llm()                                                                 # worker finished
    assert plans.get_plan(other, "en")["status"] == "generating" and len(started) == 2


def data_dir_path(region):
    return Path(store.os.environ["DATA_DIR"]) / region / "asof"


def test_local_writer_skips_test_data_and_stops_at_the_daily_cap(monkeypatch):
    monkeypatch.setenv("PLAN_AI", "local")
    monkeypatch.setenv("PLAN_WORKER", "talaab-plan-llm")
    monkeypatch.setattr(plans, "_start_worker", lambda *a: None)
    (data_dir_path("latur-2024").parent / "index.json").write_text(json.dumps({"asOf": ["2024-03-26"]}), encoding="utf-8")
    synthetic = {**MOCK, "region": {**MOCK["region"], "id": "latur-2024-synthetic"}}
    assert "test data" in plans.get_plan(synthetic, "en")["aiNote"]
    monkeypatch.setattr(plans, "MAX_LOCAL_PER_DAY", 0)
    capped = plans.get_plan(MOCK, "en")
    assert capped["status"] == "template" and "used up" in capped["aiNote"]


def test_division_plans_use_the_local_writer_but_not_bedrock(monkeypatch):
    from tests.test_division import doc
    div = doc()
    dated = Path(store.os.environ["DATA_DIR"]) / "marathwada-2026" / "division"
    dated.mkdir(parents=True)
    (dated / f"{div['asOf']}.json").write_text(json.dumps(div), encoding="utf-8")  # the latest division summary
    monkeypatch.setenv("PLAN_WORKER", "w")
    monkeypatch.setattr(plans, "_start_worker", lambda *a: None)
    monkeypatch.setenv("PLAN_AI", "on")
    assert plans.get_plan(div, "en", template={"markdown": "# t"}, region="marathwada-2026")["status"] == "template"
    monkeypatch.setenv("PLAN_AI", "local")
    assert plans.get_plan(div, "en", template={"markdown": "# t"}, region="marathwada-2026")["status"] == "generating"


def test_recompute_queues_briefings_for_the_division_and_live_districts(monkeypatch):
    from jobs import recompute
    sent = []
    divisions = [{"division": "marathwada-2026", "asOf": "2026-10-10"}]
    results = [{"region": "jalna-district-2026", "latestAsOf": "2026-10-10"}, {"region": "latur-2024", "latestAsOf": "2024-06-14"},
               {"region": "latur-2026", "latestAsOf": "2026-10-10"}, {"region": "beed-district-2026", "error": "x"}]
    assert recompute.warm_briefings(divisions, results, invoke=sent.append) == 0  # PLAN_AI off: nothing
    monkeypatch.setenv("PLAN_AI", "local")
    monkeypatch.setenv("PLAN_WORKER", "talaab-plan-llm")
    assert recompute.warm_briefings(divisions, results, invoke=sent.append) == 2
    assert sent == [{"jobs": [{"region": "marathwada-2026", "asOf": "2026-10-10"}, {"region": "jalna-district-2026", "asOf": "2026-10-10"}]}]
