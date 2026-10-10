"""AI briefing: a small open model, run inside our own Lambda, writes a short briefing on top of the plan.

Bedrock is not enabled on our AWS account yet, so the AI step runs an open-weights model (Qwen3-1.7B,
Apache-2.0) with llama.cpp in the plan Lambda (agent/llm_worker.py). A 1.7B model cannot be trusted with a
whole plan, so its job is small and checked:

  1. groups_for_snapshot / groups_for_division cut the facts a district collector or the Divisional
     Commissioner needs first into small groups (the situation, what changed, where to act, dry ponds,
     critical ponds, ponds to inspect), dates already written out, so the model only phrases, never calculates;
  2. the model writes ONE sentence per group, seeing only that group's facts, so it cannot move a fact
     from one pond or group to another (a 1.7B model given everything at once does);
  3. check_sentence rejects a sentence with a number or pond id that is not in its group (logic/guard.py),
     non-English script, the wrong length, or (inspect group) pumping stated as fact; a rejected sentence
     is re-sampled up to MAX_ATTEMPTS times, then that bullet is left out. With fewer than MIN_BULLETS
     the briefing is dropped and the deterministic plan is served alone.

The briefing is placed under the plan title; the full deterministic plan follows unchanged. Pure functions,
no I/O: the model is passed in as generate(prompt, temperature, seed) -> text.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Callable

from logic.guard import invented_numbers, numbers_in

MODEL_NAME = "Qwen3-1.7B (Q4_K_M), llama.cpp on AWS Lambda"
MAX_ATTEMPTS = 3
MIN_BULLETS = 2
MAX_WORDS = 55
TEMPERATURES = (0.4, 0.2, 0.0)
TOP_TALUKAS, TOP_PONDS, TOP_INSPECT, TOP_DISTRICTS = 3, 2, 2, 3
HEDGE = "This suggests possible unauthorised pumping; it is not proof."
PLACE_KIND_RE = re.compile(r"\b([A-Z][a-z]+) (district|taluka)\b")
POND_ID_RE = re.compile(r"\bP\d{3,5}\b")
NON_LATIN_RE = re.compile(r"[ऀ-ॿ぀-ヿ㐀-鿿가-힯]")  # Devanagari, CJK, Hangul
HEDGED_RE = re.compile(r"\b(possibl[ey]|may|might|suggests?|suspected)\b", re.I)
NAME_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
DATE_RE = re.compile(r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}\b")
# Capitalised words a sentence may use besides the names in its facts (sentence starts, months, plain English)
COMMON = set("""as since act first then pond ponds plan inspect limit restrict tankers tanker the they these this it its is are
with and most more dry critical watch water source sources users there in of district districts taluka talukas village
villages near between likely not visible yet send arrange supply alternative another all only no none so start priority
january february march april may june july august september october november december meanwhile also over""".split())
ACTION_RE = {  # what each kind of bullet must tell the officer to do
    "dry": re.compile(r"\b(source|supply|tankers?)\b", re.I),
    "critical": re.compile(r"\b(tankers?|restrict\w*|limit\w*|ration\w*)\b", re.I),
    "inspect": re.compile(r"\binspect\w*\b", re.I),
}

SYSTEM = """You write one sentence of a drought briefing for a government officer in Maharashtra, India.
Use only the FACTS given. Copy names, pond ids, numbers and dates exactly as written. Never calculate, add, round or estimate a number (no percentages, totals, populations, tanker counts or costs). Plain English, at most 40 words, no bullet, no heading."""

INSTRUCTIONS = {
    "situation": "Summarise the situation: how many ponds are dry, critical (likely to dry within a month) and on watch, and how many are not visible yet.",
    "change": "Say what changed since the last run five days earlier.",
    "where": "Say where to act first, in the order listed (the first one needs action most), with their dry and critical ponds.",
    "dry": "Name these dry ponds (id and location) and say they need another water source now.",
    "critical": "Name these critical ponds (id and location) with their likely dry range, and say to plan tankers or restrict use before then.",
    "inspect": "Name these ponds (id and location) for inspection: they shrink many times faster than their neighbours under the same sun, which suggests possible unauthorised pumping (not proof).",
}


# One worked example per kind (made-up places and numbers: if the model copies them, the checks reject the sentence)
_EX = {"area": "Example district (live, 2026)", "asOf": "1 Nov 2026"}
EXAMPLES = {
    "situation": ({**_EX, "ponds": 120, "dry": 2, "critical": 9, "watch": 14, "notVisibleYet": 30},
                  "As of 1 Nov 2026, Example district has 2 dry and 9 critical ponds out of 120, with 14 more on watch "
                  "and 30 not yet visible from space."),
    "change": ({**_EX, "since": "27 Oct 2026", "moreDry": 1, "moreCritical": 4, "fewerOnWatch": 2, "moreFlagged": 3,
                "hiddenPondsNowForecastable": 11},
               "Since 27 Oct 2026, 1 more pond has dried up and 4 more turned critical, while 11 hidden ponds became "
               "forecastable and 3 more were flagged for inspection."),
    "where": ({**_EX, "talukas": [{"taluka": "Shivpur", "dry": 1, "critical": 4}, {"taluka": "Ramnagar", "dry": 0, "critical": 3}]},
              "Act first in Shivpur taluka, with 1 dry and 4 critical ponds, then in Ramnagar taluka with 3 critical ponds."),
    "dry": ({**_EX, "dryPonds": [{"id": "P901", "location": "near Kherda, Shivpur taluka", "waterNowHa": 0.1, "fullHa": 3.2}]},
            "Pond P901 near Kherda, Shivpur taluka, is already dry, with 0.1 of its 3.2 ha left, so its users need "
            "another water source now."),
    "critical": ({**_EX, "criticalPonds": [
                     {"id": "P902", "location": "near Wadi, Ramnagar taluka", "likelyDry": "between 5 Nov 2026 and 12 Nov 2026"},
                     {"id": "P903", "location": "near Pimpri, Shivpur taluka", "likelyDry": "between 9 Nov 2026 and 20 Nov 2026"}]},
                 "Plan tankers or restrict use before pond P902 near Wadi runs dry between 5 Nov 2026 and 12 Nov 2026, "
                 "and pond P903 near Pimpri between 9 Nov 2026 and 20 Nov 2026."),
    "inspect": ({**_EX, "pondsToInspect": [{"id": "P904", "location": "near Sawargaon, Shivpur taluka", "timesFasterThanNeighbours": 6.4}]},
                "Inspect pond P904 near Sawargaon, Shivpur taluka: it is shrinking 6.4 times faster than its neighbours "
                "under the same sun, which suggests possible unauthorised pumping."),
}


def _d(iso: str | None) -> str | None:
    """'2026-10-12' -> '12 Oct 2026' (the model copies dates; it should not reformat them)."""
    if not iso:
        return None
    x = date.fromisoformat(iso)
    return f"{x.day} {x.strftime('%b')} {x.year}"


def _location(p: dict) -> str | None:
    """'near Chinchala, Umri taluka, Nanded district': one phrase the model copies (given separate fields, it
    relabels them, e.g. 'Umri district')."""
    parts = [p.get("place")] + [f"{p[k]} {k}" for k in ("taluka", "district") if p.get(k)]
    return ", ".join(x for x in parts if x) or None


def _pond(p: dict, kind: str) -> dict:
    """Only the facts this kind of sentence needs (extra facts invite the model to mix them in)."""
    row = {"id": p["id"], "location": _location(p)}
    if kind == "dry":
        row["waterNowHa"], row["fullHa"] = p.get("areaNowHa"), p.get("maxAreaHa")
    elif kind == "critical" and p.get("dryBy"):
        row["likelyDry"] = f"between {_d(p['dryBy']['earliest'])} and {_d(p['dryBy']['latest'])}"
    elif kind == "inspect":
        row["timesFasterThanNeighbours"] = p.get("shrinkVsNeighbours")
    return {k: v for k, v in row.items() if v is not None}


def _change(ch: dict) -> dict:
    """Signed differences as plain-English keys: the model copies 'moreCritical: 42' without having to read a sign."""
    out = {"since": _d(ch["since"])}
    for key, label in (("dry", "Dry"), ("critical", "Critical"), ("watch", "OnWatch"), ("flagged", "Flagged")):
        if ch[key]:
            out[("more" if ch[key] > 0 else "fewer") + label] = abs(ch[key])
    if ch["unknown"] < 0:
        out["hiddenPondsNowForecastable"] = -ch["unknown"]
    elif ch["unknown"] > 0:
        out["morePondsHiddenByCloud"] = ch["unknown"]
    return out


def _by_days(ponds) -> list[dict]:
    return sorted(ponds, key=lambda p: ((p.get("daysLeft") or {}).get("likely", 10**6), p.get("district") or "", p["id"]))


def _flagged(ponds) -> list[dict]:
    return sorted((p for p in ponds if p.get("flag") == "faster-than-sun"),
                  key=lambda p: (-(p.get("shrinkVsNeighbours") or 0), p.get("district") or "", p["id"]))


def _groups(area: str, as_of: str, counts: dict, where: dict, ponds: list[dict], flagged: list[dict],
            change: dict | None) -> list[tuple[str, dict]]:
    head = {"area": area, "asOf": _d(as_of)}
    groups = [("situation", {**head, **counts})]
    if change:
        groups.append(("change", {**head, **_change(change)}))
    if any(where.values()):
        groups.append(("where", {**head, **{k: v for k, v in where.items() if v}}))
    dry = _by_days(p for p in ponds if p["status"] == "dry")
    # only countdowns we trust: low-confidence critical calls were right far less often in the backtests
    critical = _by_days(p for p in ponds if p["status"] == "critical" and p.get("confidence") != "low")
    if dry:
        groups.append(("dry", {**head, "dryPonds": [_pond(p, "dry") for p in dry[:TOP_PONDS]]}))
    if critical:
        groups.append(("critical", {**head, "criticalPonds": [_pond(p, "critical") for p in critical[:TOP_PONDS]]}))
    if flagged:
        groups.append(("inspect", {**head, "pondsToInspect": [_pond(p, "inspect") for p in flagged[:TOP_INSPECT]]}))
    return groups


def groups_for_snapshot(doc: dict) -> list[tuple[str, dict]]:
    """One district (or the 2024 replay box): what its collector should hear first."""
    ponds = doc["ponds"]
    n = {s: sum(p["status"] == s for p in ponds) for s in ("dry", "critical", "watch", "unknown")}
    counts = {"ponds": len(ponds), "dry": n["dry"], "critical": n["critical"], "watch": n["watch"], "notVisibleYet": n["unknown"]}
    talukas = [{"taluka": t["name"], "dry": t["dry"], "critical": t["critical"]}
               for t in doc.get("talukas") or [] if t["dry"] + t["critical"]][:TOP_TALUKAS]
    return _groups(doc["region"]["name"], doc["asOf"], counts, {"talukas": talukas}, ponds, _flagged(ponds), None)


def groups_for_division(div: dict) -> list[tuple[str, dict]]:
    """The whole division (logic/division.py doc): what the Divisional Commissioner should hear first."""
    t = div["totals"]
    counts = {"districts": t["districts"], "ponds": t["ponds"], "dry": t["dry"], "critical": t["critical"],
              "watch": t["watch"], "notVisibleYet": t["unknown"]}
    where = {"districts": [{"district": r["name"], "dry": r["dry"], "critical": r["critical"]}
                           for r in div["districts"] if r["dry"] + r["critical"]][:TOP_DISTRICTS],
             "talukas": [{"taluka": g["name"], "district": g["district"], "dry": g["dry"], "critical": g["critical"]}
                         for g in div.get("talukas", []) if g["dry"] + g["critical"]][:TOP_TALUKAS]}
    return _groups(div["division"]["name"], div["asOf"], counts, where, div.get("urgentPonds", []),
                   _flagged(div.get("inspect", [])), div.get("change"))


def prompt(kind: str, facts: dict) -> str:
    """Qwen3 chat format with thinking switched off (an empty think block, as its chat template does)."""
    def ask(f: dict) -> str:
        return f"<|im_start|>user\nFACTS: {json.dumps(f, ensure_ascii=False)}\n\n{INSTRUCTIONS[kind]}<|im_end|>\n"

    think_off = "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    example_facts, example = EXAMPLES[kind]
    return (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n{ask(example_facts)}{think_off}{example}<|im_end|>\n"
            f"{ask(facts)}{think_off}")


def clean(raw: str) -> str:
    lines = raw.split("<|im_end|>")[0].strip().splitlines()
    text = lines[0].strip() if lines else ""
    return re.sub(r"^([-*•]|\d+\.)\s+", "", text).strip().strip('"').strip()


def _values(obj, key: str) -> list:
    """Every value of `key` anywhere in the facts."""
    if isinstance(obj, dict):
        return [v for k, v in obj.items() if k == key] + [x for v in obj.values() for x in _values(v, key)]
    if isinstance(obj, list):
        return [x for v in obj for x in _values(v, key)]
    return []


def strict_numbers(text: str, facts: dict) -> set[str]:
    """Stricter than logic/guard.py for these short sentences: every written date must be a date in the facts
    (the guard lets any day 1-31 through, so '11 Apr' -> '19 Apr' would pass), and every other number must be a
    non-date number of the facts."""
    vocabulary = json.dumps(facts, ensure_ascii=False)
    dates = set(DATE_RE.findall(vocabulary))
    bad = {d for d in DATE_RE.findall(text) if d not in dates}
    rest, plain = DATE_RE.sub(" ", text), DATE_RE.sub(" ", vocabulary)
    return bad | (numbers_in(rest) - numbers_in(plain))


def _one_edit(a: str, b: str) -> bool:
    """True if a and b differ by exactly one substituted, inserted or deleted letter."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def fix_names(text: str, facts: dict) -> str:
    """Correct a place name the model misspells by one letter (Qwen writes 'Udgar' for 'Udgir'), only when exactly
    one name in the sentence's own facts is that close. Anything else is left for check_sentence to reject."""
    names = set(NAME_RE.findall(json.dumps(facts, ensure_ascii=False)))
    for word in set(NAME_RE.findall(text)):
        if word.lower() in COMMON or word in names:
            continue
        close = [n for n in names if n[0] == word[0] and _one_edit(n.lower(), word.lower())]
        if len(close) == 1:
            text = re.sub(rf"\b{word}\b", close[0], text)
    return text


def check_sentence(kind: str, text: str, facts: dict) -> list[str]:
    """Reasons to reject one sentence (empty list = accepted)."""
    problems = []
    words = len(text.split())
    if not 5 <= words <= MAX_WORDS:
        problems.append(f"{words} words")
    bad = invented_numbers(text, facts) | strict_numbers(text, facts)
    if bad:
        problems.append(f"numbers not in its facts: {sorted(bad)}")
    known = set(POND_ID_RE.findall(json.dumps(facts)))
    named = set(POND_ID_RE.findall(text))
    if named - known:
        problems.append(f"pond ids not in its facts: {sorted(named - known)}")
    if kind in ("dry", "critical", "inspect") and not named:
        problems.append("names no pond")
    if not text.endswith((".", "!")):
        problems.append("unfinished sentence")
    if kind == "inspect" and re.search(r"pump", text, re.I) and not HEDGED_RE.search(text):
        problems.append("states pumping as fact")
    vocabulary = json.dumps(facts, ensure_ascii=False).lower()
    if kind == "where":  # the place that needs action most must come first
        listed = facts.get("districts") or facts.get("talukas") or []
        names = [(r.get("district") if "districts" in facts else r.get("taluka")) or "" for r in listed]
        found = {n: text.lower().find(n.lower()) for n in names if n and n.lower() in text.lower()}
        if names and (names[0] not in found or found[names[0]] != min(found.values())):
            problems.append(f"does not start with {names[0]}")
    for name, what in PLACE_KIND_RE.findall(text):
        values = [str(v).lower() for v in _values(facts, what)] + [str(facts.get("area", "")).lower()] * (what == "district")
        if f"{name} {what}".lower() not in vocabulary and not any(name.lower() in v.split() for v in values):
            problems.append(f"{name} is not a {what} in its facts")
    if kind in ACTION_RE and not ACTION_RE[kind].search(text):
        problems.append("no action")
    strange = sorted({w for w in NAME_RE.findall(text) if w.lower() not in COMMON and w.lower() not in vocabulary})
    if strange:
        problems.append(f"names not in its facts: {strange}")
    if NON_LATIN_RE.search(text):
        problems.append("not English")
    return problems


def write_briefing(groups: list[tuple[str, dict]], generate: Callable[[str, float, int], str]) -> tuple[str, dict]:
    """One checked sentence per group. Returns (markdown bullets, rejected attempts per group).
    Raises ValueError if fewer than MIN_BULLETS groups produced an accepted sentence."""
    bullets, log = [], {}
    for kind, facts in groups:
        p = prompt(kind, facts)
        log[kind] = []
        for i, temperature in enumerate(TEMPERATURES[:MAX_ATTEMPTS]):
            text = fix_names(clean(generate(p, temperature, 7 + i)), facts)
            if kind == "inspect" and text.endswith(".") and not re.search(r"pump", text, re.I):
                text = f"{text} {HEDGE}"  # the caveat is fixed wording, never left to the model
            problems = check_sentence(kind, text, facts)
            if not problems:
                bullets.append(f"- {text}")
                break
            log[kind].append(problems)
    if len(bullets) < MIN_BULLETS:
        raise ValueError(f"briefing rejected: only {len(bullets)} sentence(s) passed the checks: {log}")
    return "\n".join(bullets), log


def with_briefing(plan_markdown: str, briefing: str) -> str:
    """Briefing under the plan's title, then the unchanged deterministic plan."""
    title, _, rest = plan_markdown.partition("\n")
    note = ("_AI draft by an open model (Qwen3-1.7B) running in our own AWS Lambda. Each sentence was written from one "
            "small group of facts from this plan and checked: every number and pond id in it is in Talaab's data. "
            "The full plan below is built directly from the numbers._")
    return f"{title}\n\n## Briefing\n\n{briefing}\n\n{note}\n\n---\n{rest}"
