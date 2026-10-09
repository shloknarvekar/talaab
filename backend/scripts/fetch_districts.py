"""Fetch district boundaries from OpenStreetMap (Nominatim), once, for the district pipeline.

    python backend/scripts/fetch_districts.py [--only beed,jalna]

Writes pipeline/boundaries/<slug>-district.json ({name, nameMr, source, license, osmId, wikidata, bbox,
geometry}), the file pipeline/district.py reads. One Nominatim lookup for all districts. The Latur
file (fetched first, used by every validated run) is never overwritten. Data (c) OSM contributors, ODbL.
"""
import argparse
import json
import ssl
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUT_DIR = Path(__file__).resolve().parents[2] / "pipeline" / "boundaries"
NOMINATIM = "https://nominatim.openstreetmap.org/lookup"
# Marathwada (Chhatrapati Sambhajinagar division): slug -> OSM relation id (boundary=administrative, admin_level=5)
MARATHWADA = {
    "latur": 1991624, "beed": 1991622, "dharashiv": 1997169, "nanded": 1991143,
    "parbhani": 1991619, "hingoli": 1991161, "jalna": 1991618, "sambhajinagar": 1991614,
}
SIMPLIFY_DEG = 0.0002  # ~20 m


def tls_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated slugs (default: all Marathwada districts)")
    args = ap.parse_args()
    slugs = [s for s in (args.only.split(",") if args.only else MARATHWADA) if s != "latur"]  # latur: keep validated file
    ids = {MARATHWADA[s]: s for s in slugs}

    query = urlencode({"osm_ids": ",".join(f"R{r}" for r in ids), "format": "json", "polygon_geojson": 1,
                       "polygon_threshold": SIMPLIFY_DEG, "extratags": 1, "namedetails": 1})
    req = Request(f"{NOMINATIM}?{query}", headers={"User-Agent": "Talaab hackathon prototype (github.com/shloknarvekar/talaab)"})
    with urlopen(req, timeout=180, context=tls_context()) as r:  # noqa: S310 (fixed https URL)
        rows = json.loads(r.read())
    if len(rows) != len(ids):
        raise SystemExit(f"expected {len(ids)} districts, got {len(rows)}")

    for row in rows:
        slug = ids[int(row["osm_id"])]
        names = row.get("namedetails") or {}
        s, n, w, e = (float(x) for x in row["boundingbox"])
        base = (names.get("name:en") or names.get("name")).strip()
        base = base[: -len(" district")] if base.lower().endswith(" district") else base  # "Beed District" -> "Beed"
        doc = {"name": f"{base} district", "nameMr": names.get("name:mr"),
               "source": "OpenStreetMap via Nominatim", "license": "(c) OpenStreetMap contributors, ODbL",
               "osmId": int(row["osm_id"]), "wikidata": (row.get("extratags") or {}).get("wikidata"),
               "bbox": [w, s, e, n], "geometry": row["geojson"]}
        out = OUT_DIR / f"{slug}-district.json"
        out.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {out.name}: {doc['name']} ({doc['nameMr']}), {row['geojson']['type']}, {out.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
