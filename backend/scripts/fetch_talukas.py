"""Fetch a district's taluka (tehsil) boundaries from OpenStreetMap, once.

    python backend/scripts/fetch_talukas.py [--name latur|beed|...]

One Nominatim lookup for the district's admin_level=6 relations, simplified to ~50 m. Latur's relation ids
are listed below (checked by hand); for any other district they are found with one Overpass query for
boundary=administrative + admin_level=6 inside the district relation (its id is in
pipeline/boundaries/<name>-district.json, written by fetch_districts.py). The result is
committed as backend/jobs/places/<name>-talukas.json and bundled with the Lambdas, so OSM is never
called at run time. Data (c) OpenStreetMap contributors, ODbL.
"""
import argparse
import json
import ssl
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUT_DIR = Path(__file__).resolve().parents[1] / "jobs" / "places"
NOMINATIM = "https://nominatim.openstreetmap.org/lookup"
# OSM relation ids of each district's talukas (boundary=administrative, admin_level=6)
DISTRICTS = {
    "latur": {"district": "Latur", "relations": [10348480, 10348481, 10348482, 10348483, 10348484,
                                                  10348485, 10348486, 10348487, 10348488, 10348489]},
}
SIMPLIFY_DEG = 0.0005  # ~50 m: plenty for "which taluka is this pond in"
BOUNDARIES = Path(__file__).resolve().parents[2] / "pipeline" / "boundaries"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def discover(name: str) -> dict:
    """District name + its talukas' relation ids, from the district boundary file and one Overpass query."""
    b = json.loads((BOUNDARIES / f"{name}-district.json").read_text(encoding="utf-8"))
    query = (f'[out:json][timeout:90];rel({b["osmId"]});map_to_area->.d;'
             'rel(area.d)["boundary"="administrative"]["admin_level"="6"];out ids;')
    for url in OVERPASS:
        try:
            req = Request(url, data=urlencode({"data": query}).encode(), headers={"User-Agent": "Talaab hackathon prototype (github.com/shloknarvekar/talaab)"})
            with urlopen(req, timeout=120, context=tls_context()) as r:  # noqa: S310 (fixed https URLs)
                ids = sorted(e["id"] for e in json.loads(r.read())["elements"])
            if ids:
                return {"district": b["name"].removesuffix(" district"), "relations": ids}
        except Exception as e:  # noqa: BLE001 - try the next mirror
            print(f"{url} failed: {e}")
    raise SystemExit("could not list the talukas (Overpass busy); try again later")


def tls_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="latur")
    args = ap.parse_args()
    cfg = DISTRICTS.get(args.name) or discover(args.name)

    query = urlencode({"osm_ids": ",".join(f"R{r}" for r in cfg["relations"]), "format": "json",
                       "polygon_geojson": 1, "polygon_threshold": SIMPLIFY_DEG, "extratags": 1, "namedetails": 1})
    req = Request(f"{NOMINATIM}?{query}", headers={"User-Agent": "Talaab hackathon prototype (github.com/shloknarvekar/talaab)"})
    with urlopen(req, timeout=120, context=tls_context()) as r:  # noqa: S310 (fixed https URL)
        rows = json.loads(r.read())
    if len(rows) != len(cfg["relations"]):
        raise SystemExit(f"expected {len(cfg['relations'])} talukas, got {len(rows)}")

    talukas = []
    for row in rows:
        names = row.get("namedetails") or {}
        name = names.get("name:en") or names.get("name") or row["display_name"].split(",")[0]
        s, n, w, e = (float(x) for x in row["boundingbox"])
        talukas.append({"name": name, "nameMr": names.get("name:mr"), "osmId": int(row["osm_id"]),
                        "wikidata": (row.get("extratags") or {}).get("wikidata"),
                        "bbox": [round(w, 5), round(s, 5), round(e, 5), round(n, 5)], "geometry": row["geojson"]})
    talukas.sort(key=lambda t: t["name"])

    out = OUT_DIR / f"{args.name}-talukas.json"
    out.write_text(json.dumps({
        "source": "OpenStreetMap via Nominatim (boundary=administrative, admin_level=6), simplified ~50 m",
        "license": "Data (c) OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)",
        "fetched": date.today().isoformat(),
        "district": cfg["district"],
        "talukas": talukas,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(talukas)} talukas ({', '.join(t['name'] for t in talukas)}), {out.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
