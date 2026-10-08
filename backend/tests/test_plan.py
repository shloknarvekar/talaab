import json
import re
from pathlib import Path

from logic.plan import build_plan

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
