import json
import re
from pathlib import Path

from logic.plan import build_plan, planning_periods

MOCK = json.loads((Path(__file__).resolve().parents[2] / "web" / "public" / "mock" / "ponds.json").read_text(encoding="utf-8"))


def numbers(text):
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def test_plan_sections_and_order():
    md = build_plan(MOCK, "en")["markdown"]
    # dry pond first, then Apr-Jun critical/watch ponds, flagged pond in inspection list
    assert md.index("Already dry") < md.index("Apr–Jun 2024") < md.index("Inspect")
    assert "**P004**" in md.split("Already dry")[1].split("##")[0]
    assert "**P003**" in md.split("Inspect")[1]
    assert "2.33×" in md
    # P003 (dry ~8 Apr) is listed before P002 (dry ~16 Jun) inside the period
    period = md.split("Apr–Jun 2024")[1].split("##")[0]
    assert period.index("P003") < period.index("P002")


def test_plan_never_invents_numbers():
    """Every number in the plan must appear in the source document or be a date part / fixed rule."""
    md = build_plan(MOCK, "en")["markdown"]
    source = json.dumps(MOCK)
    allowed = numbers(source) | {str(i) for i in range(1, 32)} | {"45", "5", "2024"}
    invented = {n for n in numbers(md) if n not in allowed}
    assert not invented, invented


def test_marathi_plan():
    out = build_plan(MOCK, "mr")
    md = out["markdown"]
    assert out["language"] == "mr"
    assert "पाणीटंचाई कृती आराखडा" in md and "एप्रिल" in md
    assert "Village C (mock) जवळ" in md
    assert out["pondIds"] == build_plan(MOCK, "en")["pondIds"]


def test_empty_region():
    doc = {**MOCK, "ponds": [], "scenes": []}
    out = build_plan(doc)
    assert out["pondIds"] == [] and "None." in out["markdown"]


def test_planning_periods_follow_the_government_order():
    assert planning_periods("2026-10-08") == [(2026, 10, 12), (2027, 1, 3), (2027, 4, 6)]
    assert planning_periods("2024-03-26") == [(2024, 1, 3), (2024, 4, 6)]
    assert planning_periods("2024-05-01") == [(2024, 4, 6)]
    assert planning_periods("2026-08-15") == [(2026, 10, 12), (2027, 1, 3), (2027, 4, 6)]


def test_every_period_listed_even_when_empty_and_live_label():
    live = {**MOCK, "asOf": "2026-10-08", "live": True, "ponds": []}
    md = build_plan(live, "en")["markdown"]
    for label in ("Oct–Dec 2026", "Jan–Mar 2027", "Apr–Jun 2027"):
        assert label in md
    assert md.count("No pond is expected to dry up in this period.") == 3
    assert "Live: updated automatically" in md and "replay of past data" not in md


def test_summary_village_table_and_actions():
    md = build_plan(MOCK, "en")["markdown"]
    assert "**Summary:** 4 ponds tracked: 1 dry, 1 critical, 1 watch, 1 ok. 1 flagged for inspection." in md
    table = md.split("## By village")[1].split("\n## ")[0]
    rows = [r for r in table.splitlines() if r.startswith("| Village ") and not r.startswith("| Village |")]
    assert [r.split("|")[3].strip() for r in rows] == ["dry", "critical", "watch", "ok"]  # most urgent first
    assert "Book tankers before 5 Apr 2024" in md  # critical P003, earliest 5 Apr
    assert "Prepare tanker contracts" in md          # watch P002
    assert "replay of past data" in md
    mr = build_plan(MOCK, "mr")["markdown"]
    assert "गावनिहाय स्थिती" in mr and "टँकरची व्यवस्था करा" in mr and "सारांश" in mr
