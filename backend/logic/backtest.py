"""Backtest: replay a season pass by pass and score Talaab's predictions against what happened.

For every pass date T we build the snapshot exactly as the live system would have on T (only data
<= T), then compare with each pond's actual drying:

- actual dry window: the pond is "dry" at the first valid pass where area < 5% of its max so far
  and every later valid pass stays below. Passes are ~5 days apart, so the true date is known
  only as (last wet valid pass, first dry pass]; its midpoint is used where one date is needed.
- range hit: the predicted [earliest, latest] overlaps the actual dry window.
- too early: we predicted dry (latest) before the season's last pass, but the pond never dried.
- "dried within 30 days of T": midpoint of the dry window <= T + 30.
- critical precision: of "critical" calls (< 30 days), the share that dried within 30 days.
- critical recall: of ponds that dried within 30 days of T, the share called "critical" at T.
- lead time: days from the first "critical" call that was never withdrawn to the dry window's end.
Pure, no I/O.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from logic.countdown import DRY_FRACTION
from logic.snapshot import build_snapshot

HORIZON_DAYS = 30


def _d(s: str) -> date:
    return date.fromisoformat(s)


def actual_dry_window(history: list[dict]) -> tuple[date, date] | None:
    """(last wet valid pass, first dry valid pass) or None if the pond never dried for good."""
    valid = sorted((_d(h["date"]), float(h["areaHa"])) for h in history if h.get("valid", True))
    running_max = 0.0
    dry_flags = []
    for d, a in valid:
        running_max = max(running_max, a)
        dry_flags.append((d, running_max > 0 and a < DRY_FRACTION * running_max))
    for i, (d, is_dry) in enumerate(dry_flags):
        if is_dry and all(flag for _, flag in dry_flags[i:]):
            if i == 0:
                return None  # dry from the start: nothing to predict
            return dry_flags[i - 1][0], d
    return None


def _mid(win: tuple[date, date]) -> date:
    return win[0] + (win[1] - win[0]) / 2


def evaluate(meas: dict, start: str | None = None, end: str | None = None, heat: bool = True) -> dict:
    """Score every snapshot between start and end (scene dates). heat=False disables the ET0 scaling."""
    src = meas if heat else {**meas, "et0Climatology": {}, "et0Forecast": [], "et0": []}
    scene_dates = [s["date"] for s in meas["scenes"]]
    first, last_pass = _d(scene_dates[0]), _d(scene_dates[-1])
    lo = _d(start) if start else first + timedelta(days=20)
    hi = _d(end) if end else last_pass
    eval_dates = [d for d in scene_dates if lo <= _d(d) <= hi]

    truth = {p["id"]: actual_dry_window(p["history"]) for p in meas["ponds"]}

    hits = misses = too_early = unresolved = 0
    errors: list[int] = []
    crit_total = crit_correct = 0
    should_warn = warned = 0
    status_by_pond: dict[str, list[tuple[date, str]]] = {p["id"]: [] for p in meas["ponds"]}

    for t_str in eval_dates:
        t = _d(t_str)
        snap = build_snapshot(src, t)
        for p in snap["ponds"]:
            status_by_pond[p["id"]].append((t, p["status"]))
            win = truth[p["id"]]
            if p["status"] == "dry" or (win and win[1] <= t):
                continue  # already dry at T: nothing left to predict
            dried_soon = bool(win and (_mid(win) - t).days <= HORIZON_DAYS)
            if dried_soon:
                should_warn += 1
                warned += p["status"] == "critical"
            if p["status"] == "critical":
                crit_total += 1
                crit_correct += dried_soon
            if not p.get("dryBy"):
                continue
            e, l, likely = (_d(p["dryBy"][k]) for k in ("earliest", "latest", "likely"))
            if win:
                if e <= win[1] and l > win[0]:
                    hits += 1
                else:
                    misses += 1
                errors.append((likely - _mid(win)).days)
            elif l < last_pass:
                too_early += 1
            else:
                unresolved += 1

    ponds_out = []
    leads: list[int] = []
    for pid, win in truth.items():
        lead = first_crit = None
        if win:
            seq = [(d, s) for d, s in status_by_pond[pid] if d < win[1]]
            for i, (d, s) in enumerate(seq):  # first critical call never withdrawn before drying
                if s == "critical" and all(s2 in ("critical", "dry") for _, s2 in seq[i:]):
                    first_crit = d
                    break
            if first_crit:
                lead = (win[1] - first_crit).days
                leads.append(lead)
        ponds_out.append({
            "id": pid,
            "actualDry": {"from": win[0].isoformat(), "to": win[1].isoformat()} if win else None,
            "firstCritical": first_crit.isoformat() if first_crit else None,
            "leadDays": lead,
        })

    judged = hits + misses + too_early
    return {
        "evaluated": {"from": eval_dates[0] if eval_dates else None, "to": eval_dates[-1] if eval_dates else None,
                      "snapshots": len(eval_dates), "ponds": len(meas["ponds"]),
                      "pondsThatDried": sum(1 for w in truth.values() if w)},
        "summary": {
            "rangeHitRate": round(hits / judged, 3) if judged else None,
            "rangeHits": hits, "rangeMisses": misses, "tooEarly": too_early, "unresolved": unresolved,
            "medianErrorDays": median(errors) if errors else None,
            "medianAbsErrorDays": median(abs(x) for x in errors) if errors else None,
            "criticalPrecision": round(crit_correct / crit_total, 3) if crit_total else None,
            "criticalCalls": crit_total,
            "criticalRecall": round(warned / should_warn, 3) if should_warn else None,
            "shouldHaveWarned": should_warn,
            "medianLeadDays": median(leads) if leads else None,
            "pondsWarnedInAdvance": len(leads),
        },
        "ponds": ponds_out,
    }


def backtest(meas: dict, start: str | None = None, end: str | None = None) -> dict:
    """Main run plus the no-heat-adjustment variant, to show what the ET0 scaling is worth."""
    main = evaluate(meas, start, end, heat=True)
    no_heat = evaluate(meas, start, end, heat=False)
    return {
        "region": meas["region"],
        "synthetic": bool(meas.get("synthetic")),
        **main,
        "variants": {"noHeatAdjustment": no_heat["summary"]},
    }
