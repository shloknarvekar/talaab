"""Division view: one summary for every district of a revenue division (Marathwada). Pure function, no I/O.

The Divisional Commissioner decides which districts and talukas get tankers first, so this answers, for the
latest snapshot of each district: how many ponds are in each state, which talukas are in most trouble across
the division, which ponds are most urgent, and which to inspect first. Every number is a count or a value
copied from the district snapshots.
"""
from __future__ import annotations

STATUSES = ("dry", "critical", "watch", "ok", "unknown")
URGENCY = {"dry": 0, "critical": 1, "watch": 2, "unknown": 3, "ok": 4}
TOP_TALUKAS = 10
TOP_PONDS = 15
TOP_INSPECT = 10


def _counts(ponds: list[dict]) -> dict:
    c = {s: 0 for s in STATUSES}
    for p in ponds:
        c[p["status"] if p["status"] in c else "unknown"] += 1
    c["flagged"] = sum(p.get("flag") == "faster-than-sun" for p in ponds)
    return c


def _earliest_likely(ponds: list[dict]) -> str | None:
    dates = [p["dryBy"]["likely"] for p in ponds if p.get("dryBy") and p["status"] != "dry"]
    return min(dates) if dates else None


def _need_key(g: dict) -> tuple:
    """Most in need first: dry + critical, then watch, then the earliest likely dry date."""
    return (-(g["dry"] + g["critical"]), -g["watch"], g.get("earliestLikelyDry") or "9999", g["name"])


def _pond_row(region: str, district: str, district_mr: str | None, p: dict) -> dict:
    keep = ("id", "place", "placeMr", "taluka", "talukaMr", "status", "areaNowHa", "maxAreaHa", "dryBy", "daysLeft",
            "flag", "shrinkVsNeighbours", "lat", "lon")
    row = {"region": region, "district": district, **{k: p[k] for k in keep if p.get(k) is not None}}
    if district_mr:
        row["districtMr"] = district_mr
    return row


def summarise_division(division: dict, districts: list[tuple[str, str, dict]], names_mr: dict | None = None) -> dict:
    """division: {"id", "name", "live"}; districts: [(region id, district name, latest snapshot)];
    names_mr: optional {district name: Marathi name}."""
    names_mr = names_mr or {}
    rows, talukas, ponds = [], [], []
    for region, name, snap in districts:
        ps = snap.get("ponds", [])
        mr = names_mr.get(name)
        rows.append({"region": region, "name": name, **({"nameMr": mr} if mr else {}), "asOf": snap["asOf"], "ponds": len(ps),
                     **_counts(ps), "talukas": len(snap.get("talukas") or []), "earliestLikelyDry": _earliest_likely(ps)})
        for t in snap.get("talukas") or []:
            if t["dry"] + t["critical"] + t["watch"]:
                talukas.append({**t, "district": name, **({"districtMr": mr} if mr else {}), "region": region})
        ponds += [(region, name, mr, p) for p in ps]

    totals = {"districts": len(rows), "ponds": sum(r["ponds"] for r in rows),
              **{k: sum(r[k] for r in rows) for k in (*STATUSES, "flagged", "talukas")}}
    urgent = sorted((x for x in ponds if x[3]["status"] in ("dry", "critical", "watch")),
                    key=lambda x: (URGENCY[x[3]["status"]], (x[3].get("daysLeft") or {}).get("likely", 10**6), x[1], x[3]["id"]))
    flagged = sorted((x for x in ponds if x[3].get("flag") == "faster-than-sun"),
                     key=lambda x: (-(x[3].get("shrinkVsNeighbours") or 0), x[1], x[3]["id"]))
    return {
        "division": division,
        "asOf": max((r["asOf"] for r in rows), default=None),
        "totals": totals,
        "districts": sorted(rows, key=_need_key),
        "talukas": sorted(talukas, key=_need_key)[:TOP_TALUKAS],
        "urgentPonds": [_pond_row(*x) for x in urgent[:TOP_PONDS]],
        "inspect": [_pond_row(*x) for x in flagged[:TOP_INSPECT]],
    }
