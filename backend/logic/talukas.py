"""Per-taluka summary of a snapshot's ponds. Pure function, no I/O.

Drought is declared and water-scarcity plans are made per taluka, so a district snapshot says, for
each taluka, how many ponds are in each state and the earliest likely dry date. Every number is a
count or a date copied from the ponds.
"""
from __future__ import annotations

STATUSES = ("dry", "critical", "watch", "ok", "unknown")


def summarise(ponds: list[dict]) -> list[dict]:
    """[{name, nameMr, ponds, dry, critical, watch, ok, unknown, flagged, earliestLikelyDry}], most urgent first.

    Ponds without a taluka are left out. earliestLikelyDry is the earliest dryBy.likely of the
    taluka's ponds that are not dry yet (None if none is expected to dry).
    """
    groups: dict[str, dict] = {}
    for p in ponds:
        name = p.get("taluka")
        if not name:
            continue
        g = groups.setdefault(name, {"name": name, "nameMr": p.get("talukaMr"), "ponds": 0, **{s: 0 for s in STATUSES},
                                     "flagged": 0, "earliestLikelyDry": None})
        g["ponds"] += 1
        g[p["status"] if p["status"] in STATUSES else "unknown"] += 1
        g["flagged"] += p.get("flag") == "faster-than-sun"
        likely = (p.get("dryBy") or {}).get("likely")
        if likely and p["status"] != "dry" and (g["earliestLikelyDry"] is None or likely < g["earliestLikelyDry"]):
            g["earliestLikelyDry"] = likely
    return sorted(groups.values(), key=lambda g: (-(g["dry"] + g["critical"]), -g["watch"],
                                                   g["earliestLikelyDry"] or "9999", g["name"]))
