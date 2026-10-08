"""Deterministic water-scarcity plan writer (English / Marathi). No AI, no I/O.

Every number in the output is copied from the ponds.json document, never computed by a
model. The Bedrock plan agent (later) rewrites this into nicer prose; this template is the
fallback and the ground truth it is checked against.

Periods follow the Maharashtra scarcity plan: Oct-Dec, Jan-Mar, Apr-Jun (monsoon from July).
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
        "sun": "Over the last 45 days the sun could evaporate about **{sun} mm** of open water in this area (Open-Meteo ET0).",
        "dry_now": "Already dry: arrange alternative supply now",
        "period": "{period}: ponds likely to dry up",
        "later": "Expected to last past June (until the monsoon)",
        "unknown": "No recent clear satellite pass: check on the ground",
        "inspect": "Inspect for unauthorised extraction (shrinking faster than the sun)",
        "inspect_line": "{pond}: shrinking **{ratio}×** faster than nearby ponds under the same sun. Visit and check for pumping.",
        "pond_dry": "{pond}: {now} ha left of {max} ha (below 5%).",
        "pond_line": "{pond}: {now} ha of {max} ha now; likely dry **{likely}** (range {earliest} to {latest}, {dmin}–{dmax} days).",
        "pond_unknown": "{pond}: last measured {now} ha of {max} ha.",
        "none": "None.",
        "footer": "Drafted automatically by Talaab from Sentinel-2 satellite data (Copernicus, via AWS Open Data) and Open-Meteo weather data. All figures are measurements or ranges from our model, not exact dates. Verify on the ground before final decisions.",
        "near": "near",
        "ha": "ha",
    },
    "mr": {
        "title": "पाणीटंचाई कृती आराखडा (मसुदा): {region}",
        "asof": "माहिती दिनांक **{asof}** पर्यंतची. वापरलेले उपग्रह फोटो: {n_ok} स्वच्छ, {n_suspect} संशयास्पद.",
        "sun": "गेल्या ४५ दिवसांत या भागात सूर्याने उघड्या पाण्यातून सुमारे **{sun} मिमी** पाण्याचे बाष्पीभवन केले असते (Open-Meteo ET0).",
        "dry_now": "आधीच कोरडे: त्वरित पर्यायी पाणीपुरवठा करा",
        "period": "{period}: या काळात कोरडे होण्याची शक्यता असलेले तलाव",
        "later": "जूननंतरही (पावसाळ्यापर्यंत) टिकण्याची शक्यता",
        "unknown": "अलीकडील स्वच्छ उपग्रह फोटो नाही: प्रत्यक्ष पाहणी करा",
        "inspect": "अनधिकृत उपशासाठी तपासणी करा (सूर्यापेक्षा वेगाने आटणारे तलाव)",
        "inspect_line": "{pond}: त्याच उन्हात शेजारील तलावांपेक्षा **{ratio} पट** वेगाने आटत आहे. पंपिंग तपासण्यासाठी भेट द्या.",
        "pond_dry": "{pond}: {max} हे. पैकी फक्त {now} हे. पाणी शिल्लक (५% पेक्षा कमी).",
        "pond_line": "{pond}: सध्या {max} हे. पैकी {now} हे. पाणी; बहुधा **{likely}** पर्यंत कोरडे (अंदाज {earliest} ते {latest}, {dmin}–{dmax} दिवस).",
        "pond_unknown": "{pond}: शेवटचे मोजमाप {max} हे. पैकी {now} हे.",
        "none": "काहीही नाही.",
        "footer": "हा मसुदा Talaab ने Sentinel-2 उपग्रह माहिती (Copernicus, AWS Open Data) आणि Open-Meteo हवामान माहितीवरून आपोआप तयार केला आहे. सर्व आकडे मोजमाप किंवा अंदाजाच्या कक्षा आहेत, अचूक तारखा नाहीत. अंतिम निर्णयापूर्वी प्रत्यक्ष पाहणी करावी.",
        "near": "जवळ",
        "ha": "हे.",
    },
}

QUARTERS = [(10, 12), (1, 3), (4, 6)]  # scarcity-plan periods; Jul-Sep = monsoon


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


def _period_label(p: tuple[int, int, int], lang: str) -> str:
    year, start, end = p
    return f"{MONTHS[lang][start - 1]}–{MONTHS[lang][end - 1]} {year}"


def _period_sort_key(p: tuple[int, int, int]) -> tuple[int, int]:
    year, start, _ = p
    return year, start


def _pond_name(p: dict, t: dict) -> str:
    place = p.get("place") or ""
    if place.startswith("near ") and t["near"] != "near":
        place = f"{place[5:]} {t['near']}"
    return f"**{p['id']}** ({place})" if place else f"**{p['id']}**"


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

    def section(title: str, items: list[str]) -> None:
        lines.append("")
        lines.append(f"## {title}")
        if items:
            lines.extend(f"- {i}" for i in items)
        else:
            lines.append(t["none"])

    lines.append(f"# {t['title'].format(region=doc['region']['name'])}")
    lines.append("")
    lines.append(
        t["asof"].format(
            asof=_fmt_date(doc["asOf"], lang),
            n_ok=sum(s.get("status") == "ok" for s in scenes),
            n_suspect=sum(s.get("status") == "suspect" for s in scenes),
        )
    )
    if doc.get("sunShareMm") is not None:
        lines.append(t["sun"].format(sun=doc["sunShareMm"]))

    # 1. Already dry
    dry = [p for p in ponds if p["status"] == "dry"]
    section(t["dry_now"], [t["pond_dry"].format(pond=_pond_name(p, t), now=p["areaNowHa"], max=p["maxAreaHa"]) for p in dry])
    for p in dry:
        cite(p["id"])

    # 2. By scarcity period of the likely dry-by date, most urgent first
    shrinking = sorted((p for p in ponds if p.get("dryBy")), key=lambda p: p["dryBy"]["likely"])
    by_period: dict[tuple[int, int, int], list[dict]] = {}
    later: list[dict] = []
    for p in shrinking:
        per = _period_of(p["dryBy"]["likely"])
        if per is None:
            later.append(p)
        else:
            by_period.setdefault(per, []).append(p)
    for per in sorted(by_period, key=_period_sort_key):
        items = []
        for p in by_period[per]:
            cite(p["id"])
            items.append(
                t["pond_line"].format(
                    pond=_pond_name(p, t),
                    now=p["areaNowHa"],
                    max=p["maxAreaHa"],
                    likely=_fmt_date(p["dryBy"]["likely"], lang),
                    earliest=_fmt_date(p["dryBy"]["earliest"], lang),
                    latest=_fmt_date(p["dryBy"]["latest"], lang),
                    dmin=p["daysLeft"]["min"],
                    dmax=p["daysLeft"]["max"],
                )
            )
        section(t["period"].format(period=_period_label(per, lang)), items)
    stable = [p for p in ponds if p["status"] == "ok" and not p.get("dryBy")]
    if later or stable:
        section(t["later"], [f"{_pond_name(p, t)}: {p['areaNowHa']} / {p['maxAreaHa']} {t['ha']}" for p in later + stable])
        for p in later + stable:
            cite(p["id"])

    # 3. Ponds hidden by cloud
    unknown = [p for p in ponds if p["status"] == "unknown"]
    if unknown:
        section(t["unknown"], [t["pond_unknown"].format(pond=_pond_name(p, t), now=p["areaNowHa"], max=p["maxAreaHa"]) for p in unknown])
        for p in unknown:
            cite(p["id"])

    # 4. Inspection list
    flagged = sorted((p for p in ponds if p.get("flag") == "faster-than-sun"), key=lambda p: -p["shrinkVsNeighbours"])
    section(t["inspect"], [t["inspect_line"].format(pond=_pond_name(p, t), ratio=p["shrinkVsNeighbours"]) for p in flagged])
    for p in flagged:
        cite(p["id"])

    lines.append("")
    lines.append(f"_{t['footer']}_")
    return {"markdown": "\n".join(lines), "pondIds": cited, "source": "template", "asOf": doc["asOf"], "language": lang}
