"""Deterministic water-scarcity plan writer (English / Marathi). No AI, no I/O.

Every number in the output is copied from the ponds.json document (plus pond counts), never
computed by a model. The Bedrock plan agent rewrites it into fuller prose; this template is the
fallback and the ground truth the AI plan is checked against.

Structure follows the Maharashtra order (25 Sep 2026): a separate plan for each scarcity period
Oct-Dec, Jan-Mar and Apr-Jun; the monsoon is expected from July.
"""
from __future__ import annotations

from datetime import date

MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
}

T = {
    "en": {
        "title": "Water-scarcity action plan (draft): {region}",
        "asof": "Data as of **{asof}**. Satellite passes used: {n_ok} clear, {n_suspect} suspect.",
        "replay": "This is a replay of past data: every figure uses only what was known on {asof}.",
        "live": "Live: updated automatically after each satellite pass (about every 5 days).",
        "sun": "Over the last 45 days the sun could evaporate about **{sun} mm** of open water in this area (Open-Meteo ET0).",
        "summary": "**Summary:** {n} ponds tracked: {dry} dry, {critical} critical, {watch} watch, {ok} ok{unknown}. {flagged} flagged for inspection.",
        "summary_unknown": ", {n} not visible",
        "talukas": "By taluka",
        "taluka_head": "| Taluka | Ponds | Dry | Critical | Watch | Not visible | Flagged | Earliest likely dry date |",
        "taluka_word": "taluka",
        "villages": "By village",
        "village_head": "| Village | Ponds | Most urgent | Earliest likely dry date |",
        "villages_more": "{n} more villages have only ok or not-yet-visible ponds (see the map).",
        "grouped": "**{taluka}** ({n}): {ids}",
        "unnamed": "Unnamed location",
        "to_monsoon": "lasts to monsoon",
        "dry_now": "Already dry: arrange alternative supply now",
        "period": "{period}: ponds likely to dry up",
        "period_empty": "No pond is expected to dry up in this period.",
        "later": "Expected to last until the monsoon",
        "unknown": "No recent clear satellite pass: check on the ground",
        "inspect": "Inspect for unauthorised extraction (shrinking faster than the sun)",
        "inspect_line": "{pond}: shrinking **{ratio}×** faster than nearby ponds under the same sun. Inspect within a week; this suggests pumping but is not proof.",
        "pond_dry": "{pond}: {now} ha left of {max} ha (below 5%). Arrange tanker or alternative supply now.",
        "pond_line": "{pond}: {now} ha of {max} ha now; likely dry **{likely}** (range {earliest} to {latest}, {dmin}–{dmax} days). {action}",
        "pond_later": "{pond}: {now} ha of {max} ha. Routine monitoring.",
        "pond_unknown": "{pond}: last measured {now} ha of {max} ha. Send a field check.",
        "act_critical": "Book tankers before {earliest}; restrict non-drinking use now.",
        "act_watch": "Prepare tanker contracts; re-check after each satellite pass.",
        "act_ok": "Routine monitoring.",
        "none": "None.",
        "status": {"dry": "dry", "critical": "critical", "watch": "watch", "ok": "ok", "unknown": "not visible"},
        "footer": "Drafted automatically by Talaab from Sentinel-2 satellite data (Copernicus, via AWS Open Data) and Open-Meteo weather data; village names (c) OpenStreetMap contributors. All figures are measurements or ranges from our model, not exact dates. Verify on the ground before final decisions.",
        "near": "near",
    },
    "mr": {
        "title": "पाणीटंचाई कृती आराखडा (मसुदा): {region}",
        "asof": "माहिती दिनांक **{asof}** पर्यंतची. वापरलेले उपग्रह फोटो: {n_ok} स्वच्छ, {n_suspect} संशयास्पद.",
        "replay": "ही भूतकाळातील माहितीची पुनरावृत्ती (replay) आहे: प्रत्येक आकडा फक्त {asof} पर्यंत उपलब्ध माहितीवर आधारित आहे.",
        "live": "थेट: प्रत्येक उपग्रह फेरीनंतर (सुमारे दर ५ दिवसांनी) आपोआप अद्ययावत होते.",
        "sun": "गेल्या ४५ दिवसांत या भागात सूर्याने उघड्या पाण्यातून सुमारे **{sun} मिमी** पाण्याचे बाष्पीभवन केले असते (Open-Meteo ET0).",
        "summary": "**सारांश:** एकूण {n} तलाव: {dry} कोरडे, {critical} गंभीर, {watch} लक्ष ठेवा, {ok} सुरक्षित{unknown}. {flagged} तलाव तपासणीसाठी.",
        "summary_unknown": ", {n} दिसत नाहीत",
        "talukas": "तालुकानिहाय स्थिती",
        "taluka_head": "| तालुका | तलाव | कोरडे | गंभीर | लक्ष ठेवा | दिसत नाहीत | तपासणीसाठी | सर्वात लवकर कोरडे होण्याची संभाव्य तारीख |",
        "taluka_word": "तालुका",
        "villages": "गावनिहाय स्थिती",
        "village_head": "| गाव | तलाव | सर्वात गंभीर स्थिती | सर्वात लवकर कोरडे होण्याची संभाव्य तारीख |",
        "villages_more": "आणखी {n} गावांतील तलाव सुरक्षित आहेत किंवा अजून दिसत नाहीत (नकाशा पाहा).",
        "grouped": "**{taluka}** ({n}): {ids}",
        "unnamed": "नाव नसलेले ठिकाण",
        "to_monsoon": "पावसाळ्यापर्यंत टिकेल",
        "dry_now": "आधीच कोरडे: त्वरित पर्यायी पाणीपुरवठा करा",
        "period": "{period}: या काळात कोरडे होण्याची शक्यता असलेले तलाव",
        "period_empty": "या काळात कोणताही तलाव कोरडा होण्याची शक्यता नाही.",
        "later": "पावसाळ्यापर्यंत टिकण्याची शक्यता",
        "unknown": "अलीकडील स्वच्छ उपग्रह फोटो नाही: प्रत्यक्ष पाहणी करा",
        "inspect": "अनधिकृत उपशासाठी तपासणी करा (सूर्यापेक्षा वेगाने आटणारे तलाव)",
        "inspect_line": "{pond}: त्याच उन्हात शेजारील तलावांपेक्षा **{ratio} पट** वेगाने आटत आहे. आठवड्याभरात तपासणी करा; हे पंपिंगचे संकेत आहेत, पुरावा नाही.",
        "pond_dry": "{pond}: {max} हे. पैकी फक्त {now} हे. पाणी शिल्लक (५% पेक्षा कमी). त्वरित टँकर किंवा पर्यायी पाणीपुरवठ्याची व्यवस्था करा.",
        "pond_line": "{pond}: सध्या {max} हे. पैकी {now} हे. पाणी; बहुधा **{likely}** पर्यंत कोरडे (अंदाज {earliest} ते {latest}, {dmin}–{dmax} दिवस). {action}",
        "pond_later": "{pond}: {max} हे. पैकी {now} हे. नियमित देखरेख.",
        "pond_unknown": "{pond}: शेवटचे मोजमाप {max} हे. पैकी {now} हे. प्रत्यक्ष पाहणी पाठवा.",
        "act_critical": "{earliest} पूर्वी टँकरची व्यवस्था करा; पिण्याव्यतिरिक्त पाणीवापरावर आत्ताच निर्बंध घाला.",
        "act_watch": "टँकर करारांची तयारी करा; प्रत्येक उपग्रह फेरीनंतर पुन्हा तपासा.",
        "act_ok": "नियमित देखरेख.",
        "none": "काहीही नाही.",
        "status": {"dry": "कोरडे", "critical": "गंभीर", "watch": "लक्ष ठेवा", "ok": "सुरक्षित", "unknown": "दिसत नाही"},
        "footer": "हा मसुदा Talaab ने Sentinel-2 उपग्रह माहिती (Copernicus, AWS Open Data) आणि Open-Meteo हवामान माहितीवरून (गावांची नावे: OpenStreetMap) आपोआप तयार केला आहे. सर्व आकडे मोजमाप किंवा अंदाजाच्या कक्षा आहेत, अचूक तारखा नाहीत. अंतिम निर्णयापूर्वी प्रत्यक्ष पाहणी करावी.",
        "near": "जवळ",
    },
}

QUARTERS = [(10, 12), (1, 3), (4, 6)]  # scarcity-plan periods; Jul-Sep = monsoon
URGENCY = {"dry": 0, "critical": 1, "watch": 2, "unknown": 3, "ok": 4}
# District scale (hundreds of ponds): the village table keeps only villages that need action, and the
# low-priority lists (lasting to monsoon, not visible) become one line of pond ids per taluka.
MAX_VILLAGE_ROWS = 30
MAX_LIST_ITEMS = 25


def _fmt_date(iso: str, lang: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def _period_of(iso: str) -> tuple[int, int, int] | None:
    """(year, start_month, end_month) of the scarcity period containing the date, None for Jul-Sep."""
    d = date.fromisoformat(iso)
    for start, end in QUARTERS:
        if start <= d.month <= end:
            return d.year, start, end
    return None


def planning_periods(as_of: str) -> list[tuple[int, int, int]]:
    """Scarcity periods from the one containing as_of (or the next, in the monsoon) to the next June."""
    d = date.fromisoformat(as_of)
    if d.month >= 7:  # Jul-Dec: Oct-Dec this year, then Jan-Mar and Apr-Jun next year
        return [(d.year, 10, 12), (d.year + 1, 1, 3), (d.year + 1, 4, 6)]
    if d.month <= 3:
        return [(d.year, 1, 3), (d.year, 4, 6)]
    return [(d.year, 4, 6)]


def _period_label(p: tuple[int, int, int], lang: str) -> str:
    year, start, end = p
    return f"{MONTHS[lang][start - 1]}–{MONTHS[lang][end - 1]} {year}"


def _village(p: dict, t: dict) -> str:
    if t["near"] != "near" and p.get("placeMr"):
        return p["placeMr"]
    place = (p.get("place") or "").strip()
    if place.lower().startswith("near "):
        place = place[5:].strip()
    return place or t["unnamed"]


def _taluka(p: dict, t: dict) -> str:
    """Taluka name in the plan's language ('' if the pond has none)."""
    return (p.get("talukaMr") if t["near"] != "near" else None) or p.get("taluka") or ""


def _pond_name(p: dict, t: dict) -> str:
    if t["near"] != "near" and p.get("placeMr"):
        place = f"{p['placeMr']} {t['near']}"
    else:
        place = (p.get("place") or "").strip()
        if place.lower().startswith("near ") and t["near"] != "near":
            place = f"{place[5:].strip()} {t['near']}"
    taluka = _taluka(p, t)
    where = ", ".join(x for x in (place, f"{taluka} {t['taluka_word']}" if taluka else "") if x)
    return f"**{p['id']}** ({where})" if where else f"**{p['id']}**"


def build_plan(doc: dict, language: str = "en") -> dict:
    lang = language if language in T else "en"
    t = T[lang]
    ponds = doc["ponds"]
    scenes = doc.get("scenes", [])
    lines: list[str] = []
    cited: list[str] = []

    def cite(pid: str) -> None:
        if pid not in cited:
            cited.append(pid)

    def section(title: str, items: list[str], empty: str | None = None) -> None:
        lines.append("")
        lines.append(f"## {title}")
        if items:
            lines.extend(f"- {i}" for i in items)
        else:
            lines.append(empty or t["none"])

    # Header
    lines.append(f"# {t['title'].format(region=doc['region']['name'])}")
    lines.append("")
    asof_txt = _fmt_date(doc["asOf"], lang)
    lines.append(t["asof"].format(asof=asof_txt, n_ok=sum(s.get("status") == "ok" for s in scenes),
                                  n_suspect=sum(s.get("status") == "suspect" for s in scenes)))
    lines.append(t["live"] if doc.get("live") else t["replay"].format(asof=asof_txt))
    if doc.get("sunShareMm") is not None:
        lines.append(t["sun"].format(sun=doc["sunShareMm"]))

    counts = {k: sum(p["status"] == k for p in ponds) for k in URGENCY}
    flagged = sorted((p for p in ponds if p.get("flag") == "faster-than-sun"), key=lambda p: -p["shrinkVsNeighbours"])
    lines.append("")
    lines.append(t["summary"].format(
        n=len(ponds), dry=counts["dry"], critical=counts["critical"], watch=counts["watch"], ok=counts["ok"],
        unknown=t["summary_unknown"].format(n=counts["unknown"]) if counts["unknown"] else "", flagged=len(flagged)))

    # By taluka: drought is declared and planned per taluka (counts copied from doc["talukas"])
    if doc.get("talukas"):
        lines.append("")
        lines.append(f"## {t['talukas']}")
        lines.append("")
        lines.append(t["taluka_head"])
        lines.append("|---|---|---|---|---|---|---|---|")
        for g in doc["talukas"]:
            name = (g.get("nameMr") if lang == "mr" else None) or g["name"]
            first = g.get("earliestLikelyDry")
            when = "–" if not first else (t["to_monsoon"] if _period_of(first) not in planning_periods(doc["asOf"])
                                          else _fmt_date(first, lang))
            lines.append(f"| {name} | {g['ponds']} | {g['dry']} | {g['critical']} | {g['watch']} | {g['unknown']} | {g['flagged']} | {when} |")

    # By village: worst status first, then earliest likely dry date
    villages: dict[str, list[dict]] = {}
    for p in ponds:
        villages.setdefault(_village(p, t), []).append(p)
    if villages:
        rows = []
        for name, vp in villages.items():
            worst = min(vp, key=lambda p: URGENCY[p["status"]])["status"]
            dates = sorted(p["dryBy"]["likely"] for p in vp if p.get("dryBy"))
            rows.append((URGENCY[worst], dates[0] if dates else "9999", name, vp, worst, dates))
        rows.sort(key=lambda r: (r[0], r[1], r[2]))
        hidden = 0
        if len(rows) > MAX_VILLAGE_ROWS:  # district scale: only villages that need action
            keep = [r for r in rows if r[0] <= URGENCY["watch"] or any(p.get("flag") for p in r[3])]
            hidden, rows = len(rows) - len(keep), keep
        lines.append("")
        lines.append(f"## {t['villages']}")
        lines.append("")
        lines.append(t["village_head"])
        lines.append("|---|---|---|---|")
        for _, _, name, vp, worst, dates in rows:
            ids = ", ".join(p["id"] for p in sorted(vp, key=lambda p: p["id"]))
            if not dates:
                when = "–"
            elif _period_of(dates[0]) not in planning_periods(doc["asOf"]):  # monsoon or next season
                when = t["to_monsoon"]
            else:
                when = _fmt_date(dates[0], lang)
            lines.append(f"| {name} | {ids} | {t['status'][worst]} | {when} |")
        if hidden:
            lines.append("")
            lines.append(t["villages_more"].format(n=hidden))

    # 1. Already dry
    dry = [p for p in ponds if p["status"] == "dry"]
    section(t["dry_now"], [t["pond_dry"].format(pond=_pond_name(p, t), now=p["areaNowHa"], max=p["maxAreaHa"]) for p in dry])
    for p in dry:
        cite(p["id"])

    # 2. One section per scarcity period (the order asks for a plan per period), most urgent first
    shrinking = sorted((p for p in ponds if p.get("dryBy") and p["status"] != "dry"), key=lambda p: p["dryBy"]["likely"])
    by_period: dict[tuple[int, int, int], list[dict]] = {}
    later: list[dict] = []
    periods = planning_periods(doc["asOf"])
    for p in shrinking:
        per = _period_of(p["dryBy"]["likely"])
        # Past this season's last planned June (monsoon, or next year's dry season): it lasts
        # until the monsoon, and belongs to next season's plan, not this one.
        if per is None or per not in periods:
            later.append(p)
        else:
            by_period.setdefault(per, []).append(p)
    for per in periods:
        items = []
        for p in by_period.get(per, []):
            cite(p["id"])
            earliest = _fmt_date(p["dryBy"]["earliest"], lang)
            action = t["act_critical"].format(earliest=earliest) if p["status"] == "critical" else (
                t["act_watch"] if p["status"] == "watch" else t["act_ok"])
            items.append(t["pond_line"].format(
                pond=_pond_name(p, t), now=p["areaNowHa"], max=p["maxAreaHa"],
                likely=_fmt_date(p["dryBy"]["likely"], lang), earliest=earliest,
                latest=_fmt_date(p["dryBy"]["latest"], lang),
                dmin=p["daysLeft"]["min"], dmax=p["daysLeft"]["max"], action=action))
        section(t["period"].format(period=_period_label(per, lang)), items, empty=t["period_empty"])

    def grouped(items: list[dict]) -> list[str]:
        """One line of pond ids per taluka (district scale), largest group first."""
        by: dict[str, list[str]] = {}
        for p in items:
            by.setdefault(_taluka(p, t) or t["unnamed"], []).append(p["id"])
        return [t["grouped"].format(taluka=name, n=len(ids), ids=", ".join(sorted(ids)))
                for name, ids in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0]))]

    # 3. Lasting until the monsoon (incl. stable ponds)
    stable = [p for p in ponds if p["status"] == "ok" and not p.get("dryBy")]
    if later or stable:
        lasting = later + stable
        section(t["later"], grouped(lasting) if len(lasting) > MAX_LIST_ITEMS else
                [t["pond_later"].format(pond=_pond_name(p, t), now=p["areaNowHa"], max=p["maxAreaHa"]) for p in lasting])
        for p in lasting:
            cite(p["id"])

    # 4. Hidden by cloud
    unknown = [p for p in ponds if p["status"] == "unknown"]
    if unknown:
        section(t["unknown"], grouped(unknown) if len(unknown) > MAX_LIST_ITEMS else
                [t["pond_unknown"].format(pond=_pond_name(p, t), now=p["areaNowHa"], max=p["maxAreaHa"]) for p in unknown])
        for p in unknown:
            cite(p["id"])

    # 5. Inspection list
    section(t["inspect"], [t["inspect_line"].format(pond=_pond_name(p, t), ratio=p["shrinkVsNeighbours"]) for p in flagged])
    for p in flagged:
        cite(p["id"])

    lines.append("")
    lines.append(f"_{t['footer']}_")
    return {"markdown": "\n".join(lines), "pondIds": cited, "source": "template", "asOf": doc["asOf"], "language": lang}
