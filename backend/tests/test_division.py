"""Division view: one summary across districts (logic/division.py) and the division plan (logic/plan.py)."""
from logic.division import TOP_PONDS, TOP_TALUKAS, summarise_division
from logic.plan import build_division_plan
from logic.talukas import summarise as summarise_talukas

DIVISION = {"id": "marathwada-2026", "name": "Marathwada (live, 2026)", "nameMr": "मराठवाडा (थेट, 2026)", "live": True}


def pond(pid, status, taluka, likely=None, days=None, flag=None, ratio=None):
    return {"id": pid, "status": status, "taluka": taluka, "talukaMr": None, "place": f"near V{pid}", "areaNowHa": 1.0,
            "maxAreaHa": 4.0, "dryBy": {"earliest": likely, "likely": likely, "latest": likely} if likely else None,
            "daysLeft": {"min": days, "likely": days, "max": days} if days is not None else None,
            "flag": flag, "shrinkVsNeighbours": ratio, "lat": 18.4, "lon": 76.5}


def snap(as_of, ponds):
    return {"asOf": as_of, "ponds": ponds, "talukas": summarise_talukas(ponds)}


JALNA = snap("2026-10-10", [pond("P001", "critical", "Jafferabad", "2026-10-15", 5), pond("P002", "dry", "Jafferabad", days=0),
                            pond("P003", "watch", "Ambad", "2026-11-30", 51, "faster-than-sun", 4.2), pond("P004", "ok", "Ambad")])
BEED = snap("2026-10-09", [pond("P001", "critical", "Ashti", "2026-10-12", 2), pond("P002", "unknown", "Ashti"),
                           pond("P003", "ok", "Kaij", flag="faster-than-sun", ratio=2.5)])


def doc(names_mr=None):
    return summarise_division(DIVISION, [("beed-district-2026", "Beed", BEED), ("jalna-district-2026", "Jalna", JALNA)], names_mr)


def test_totals_and_district_rows():
    d = doc()
    assert d["asOf"] == "2026-10-10"  # the newest district snapshot
    assert d["totals"] == {"districts": 2, "ponds": 7, "dry": 1, "critical": 2, "watch": 1, "ok": 2, "unknown": 1,
                           "flagged": 2, "talukas": 4}
    jalna, beed = d["districts"]  # most in need first: Jalna has dry + critical = 2, Beed 1
    assert (jalna["name"], jalna["ponds"], jalna["dry"], jalna["critical"], jalna["earliestLikelyDry"]) == ("Jalna", 4, 1, 1, "2026-10-15")
    assert (beed["name"], beed["asOf"], beed["earliestLikelyDry"]) == ("Beed", "2026-10-09", "2026-10-12")


def test_talukas_in_need_across_districts():
    names = [(t["name"], t["district"]) for t in doc()["talukas"]]
    assert names == [("Jafferabad", "Jalna"), ("Ashti", "Beed"), ("Ambad", "Jalna")]  # Kaij has nothing to act on


def test_all_talukas_are_listed_for_the_district_drill_down():
    d = doc()
    assert [(t["name"], t["district"]) for t in d["allTalukas"]] == [("Jafferabad", "Jalna"), ("Ashti", "Beed"),
                                                                     ("Ambad", "Jalna"), ("Kaij", "Beed")]
    assert sum(t["ponds"] for t in d["allTalukas"]) == d["totals"]["ponds"] and len(d["talukas"]) <= TOP_TALUKAS
    assert all(t["region"] for t in d["allTalukas"])


def test_change_since_the_run_before():
    before_jalna = snap("2026-10-05", [pond("P001", "watch", "Jafferabad", "2026-11-01", 27), pond("P002", "critical", "Jafferabad", "2026-10-09", 4),
                                       pond("P003", "watch", "Ambad", "2026-11-30", 56), pond("P004", "ok", "Ambad")])
    d = summarise_division(DIVISION, [("beed-district-2026", "Beed", BEED), ("jalna-district-2026", "Jalna", JALNA)],
                           previous={"jalna-district-2026": before_jalna}, since="2026-10-05")
    jalna, beed = d["districts"]
    # Jalna: P002 critical -> dry, P001 watch -> critical, P003 newly flagged
    assert jalna["change"] == {"since": "2026-10-05", "dry": 1, "critical": 0, "watch": -1, "unknown": 0, "flagged": 1}
    assert "change" not in beed  # no earlier snapshot: not compared, and the totals say only 1 district was
    assert d["change"] == {"since": "2026-10-05", "districts": 1, "dry": 1, "critical": 0, "watch": -1, "unknown": 0, "flagged": 1}
    assert doc()["change"] is None  # nothing to compare with
    same_day = summarise_division(DIVISION, [("jalna-district-2026", "Jalna", JALNA)], previous={"jalna-district-2026": JALNA})
    assert same_day["change"] is None  # a snapshot is never compared with itself
    en = build_division_plan(d, "en")["markdown"]
    assert "**Change since 5 Oct 2026** (one run earlier, 1 of 2 districts compared): dry +1, critical +0, watch -1, flagged +1." in en
    assert "पासूनचा बदल" in build_division_plan(d, "mr")["markdown"] and "Change since" not in build_division_plan(doc(), "en")["markdown"]


def test_urgent_ponds_and_inspection_list():
    d = doc()
    assert [(p["district"], p["id"], p["status"]) for p in d["urgentPonds"]] == [
        ("Jalna", "P002", "dry"), ("Beed", "P001", "critical"), ("Jalna", "P001", "critical"), ("Jalna", "P003", "watch")]
    assert all(p["region"] for p in d["urgentPonds"]) and len(d["urgentPonds"]) <= TOP_PONDS
    assert [(p["district"], p["id"]) for p in d["inspect"]] == [("Jalna", "P003"), ("Beed", "P003")]  # by ratio


def test_division_plan_english_and_marathi():
    en = build_division_plan(doc(), "en")
    md = en["markdown"]
    assert md.index("## By district") < md.index("## Talukas needing action first") < md.index("## Most urgent ponds")
    assert "| Jalna | 4 | 1 | 1 | 1 | 0 | 1 | 15 Oct 2026 |" in md
    assert "**P002** (near VP002, Jafferabad taluka, Jalna district)" in md
    assert "4.2×" in md and "Data as of **10 Oct 2026**" in md
    assert en["source"] == "template" and en["language"] == "en"
    mr = build_division_plan(doc({"Jalna": "जालना", "Beed": "बीड"}), "mr")["markdown"]
    assert "जिल्हानिहाय स्थिती" in mr and "मराठवाडा (थेट, 2026)" in mr and "ऑक्टोबर" in mr
    assert "| जालना | 4 |" in mr and "जालना जिल्हा" in mr  # Marathi district names in the table and pond lines
