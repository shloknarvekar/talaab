"""Fetch named places (villages, hamlets, towns) around a region from OpenStreetMap, once.

    python backend/scripts/fetch_places.py [--name latur] [--bbox 76.47 18.33 76.62 18.48] [--margin 0.05]

One Overpass API request; the result is committed as backend/jobs/places/<name>.json and bundled
with the Lambda, so OSM is never called at run time. Data (c) OpenStreetMap contributors, ODbL.
"""
import argparse
import json
import ssl
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen

OVERPASS_MIRRORS = [  # public Overpass instances, tried in order
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
OUT_DIR = Path(__file__).resolve().parents[1] / "jobs" / "places"
TYPES = "city|town|village|hamlet|suburb"


def tls_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def is_devanagari(s: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="latur")
    ap.add_argument("--bbox", nargs=4, type=float, default=[76.47, 18.33, 76.62, 18.48], metavar=("W", "S", "E", "N"))
    ap.add_argument("--margin", type=float, default=0.05, help="degrees added on every side (~5 km)")
    args = ap.parse_args()

    w, s, e, n = args.bbox
    m = args.margin
    query = f'[out:json][timeout:60];node["place"~"^({TYPES})$"]["name"]({s - m},{w - m},{n + m},{e + m});out body;'
    elements = None
    for url in OVERPASS_MIRRORS:
        req = Request(url, data=urlencode({"data": query}).encode(),
                      headers={"User-Agent": "Talaab hackathon prototype (github.com/shloknarvekar/talaab)"})
        try:
            with urlopen(req, timeout=90, context=tls_context()) as r:  # noqa: S310 (fixed https URLs)
                elements = json.loads(r.read())["elements"]
            print(f"fetched from {url}")
            break
        except (URLError, TimeoutError, json.JSONDecodeError) as err:
            print(f"{url} failed: {err}")
    if elements is None:
        raise SystemExit("all Overpass mirrors failed; try again later")

    places = []
    for el in elements:
        tags = el["tags"]
        name = tags.get("name:en") or tags["name"]
        name_mr = tags.get("name:mr") or (tags["name"] if is_devanagari(tags["name"]) else None)
        if is_devanagari(name):  # no English name at all: keep the Marathi one in both slots
            name = tags.get("name:en") or name
        places.append({"name": name, "nameMr": name_mr, "type": tags["place"],
                       "lat": round(el["lat"], 5), "lon": round(el["lon"], 5)})
    places.sort(key=lambda p: (p["name"], p["lat"]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.name}.json"
    out.write_text(json.dumps({
        "source": "OpenStreetMap via Overpass API",
        "license": "Data (c) OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)",
        "fetched": date.today().isoformat(),
        "bbox": [w - m, s - m, e + m, n + m],
        "places": places,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    by_type = {}
    for p in places:
        by_type[p["type"]] = by_type.get(p["type"], 0) + 1
    print(f"wrote {out}: {len(places)} places {by_type}; with Marathi name: {sum(1 for p in places if p['nameMr'])}")


if __name__ == "__main__":
    main()
