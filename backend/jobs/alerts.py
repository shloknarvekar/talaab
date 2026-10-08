"""Critical-pond alerts: tell the district officer when something changes, not on every run.

After each recompute of a LIVE region, the latest snapshot is compared with the state remembered
from the previous run. A pond that newly turns critical, newly dries up, or is newly flagged
"faster than the sun" goes into one email (Amazon SNS). Ponds are keyed by location, not id,
because ids can be renumbered when the pipeline re-cleans its data.
"""
from __future__ import annotations

from datetime import date

REASONS = {
    "critical": "turned CRITICAL: likely dry within 30 days",
    "dry": "has DRIED UP: arrange alternative supply",
    "flag": "is shrinking FASTER THAN THE SUN: inspect for unauthorised pumping",
}
ORDER = {"dry": 0, "critical": 1, "flag": 2}


def pond_key(p: dict) -> str:
    return f"{round(p['lat'], 4)},{round(p['lon'], 4)}"


def alert_state(snap: dict) -> dict:
    return {pond_key(p): {"id": p["id"], "status": p["status"], "flag": p.get("flag")} for p in snap["ponds"]}


def new_alerts(prev_state: dict, snap: dict) -> list[dict]:
    """One entry per (pond, reason) that is new since prev_state, most urgent first."""
    out = []
    for p in snap["ponds"]:
        before = prev_state.get(pond_key(p), {})
        reasons = []
        if p["status"] == "dry" and before.get("status") != "dry":
            reasons.append("dry")
        elif p["status"] == "critical" and before.get("status") not in ("critical", "dry"):
            reasons.append("critical")
        if p.get("flag") == "faster-than-sun" and not before.get("flag"):
            reasons.append("flag")
        for r in reasons:
            out.append({"id": p["id"], "place": p.get("place") or "", "reason": r, "status": p["status"],
                        "areaNowHa": p.get("areaNowHa"), "maxAreaHa": p.get("maxAreaHa"),
                        "dryBy": p.get("dryBy"), "ratio": p.get("shrinkVsNeighbours")})
    return sorted(out, key=lambda a: (ORDER[a["reason"]], a["id"]))


def _d(iso: str) -> str:
    x = date.fromisoformat(iso)
    return f"{x.day} {x.strftime('%b')} {x.year}"


def format_alert(region_name: str, as_of: str, alerts: list[dict], site_url: str) -> tuple[str, str]:
    """(subject <= 100 chars, plain-text body). Every number is copied from the snapshot."""
    n = len({a["id"] for a in alerts})
    subject = f"Talaab: {n} pond{'s' if n != 1 else ''} need action in {region_name}"[:100]
    lines = [f"Talaab update for {region_name}, as of {_d(as_of)}.", ""]
    for a in alerts:
        where = f" ({a['place']})" if a["place"] else ""
        lines.append(f"- {a['id']}{where} {REASONS[a['reason']]}.")
        if a["reason"] == "critical" and a.get("dryBy"):
            lines.append(f"    Likely dry {_d(a['dryBy']['likely'])} (range {_d(a['dryBy']['earliest'])} to {_d(a['dryBy']['latest'])}); "
                         f"{a['areaNowHa']} ha of {a['maxAreaHa']} ha left.")
        if a["reason"] == "flag" and a.get("ratio"):
            lines.append(f"    Shrinking {a['ratio']}x faster than nearby ponds under the same sun. This suggests pumping; it is not proof.")
        if a["reason"] == "dry":
            lines.append(f"    {a['areaNowHa']} ha left of {a['maxAreaHa']} ha (below 5%).")
    lines += ["", f"Map and full plan: {site_url}",
              "Forecasts are ranges from Sentinel-2 satellite measurements and Open-Meteo heat forecasts; verify on the ground.",
              "You receive this because you subscribed to Talaab alerts (Amazon SNS)."]
    return subject, "\n".join(lines)
