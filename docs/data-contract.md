# Data contract: `ponds.json`

Every part of Talaab builds against this shape: the pipeline writes it, the API serves it, the web app renders it, and the plan agent reads it.
A working example with 4 ponds lives at [`web/public/mock/ponds.json`](../web/public/mock/ponds.json).

## Shape

```jsonc
{
  "region": {
    "id": "latur-2024",                 // slug, used in API ?region=
    "name": "Latur (2024 replay)",      // display name; replays MUST say so
    "bbox": [76.47, 18.33, 76.62, 18.48] // [minLon, minLat, maxLon, maxLat]
  },
  "asOf": "2024-03-26",                 // everything below uses only data dated <= asOf
  "sunShareMm": 239.2,                  // region ET0 total (mm) over the 45-day fit window ending asOf
  "scenes": [                           // Sentinel-2 passes used, oldest first, all <= asOf
    { "date": "2024-01-16", "id": "S2B_43QFA_20240116_0_L2A", "status": "ok" }   // "ok" | "suspect"
  ],
  "ponds": [
    {
      "id": "P003",                     // P001, P002… sorted by area on the reference date (largest first)
      "lat": 18.3753, "lon": 76.535,    // pond centroid, WGS84
      "place": "near <village>",        // nearest OSM village within 5 km (or the pipeline's own label); "" if none
      "placeMr": "<गाव>",               // optional: Marathi village name from OSM
      "taluka": "Udgir",                // optional: the taluka (tehsil) the pond lies in (OSM admin_level 6)
      "talukaMr": "उदगीर",              // optional: its Marathi name
      "maxAreaHa": 33.3,                // max valid area seen up to asOf (ha)
      "areaNowHa": 8.6,                 // latest valid area up to asOf (ha)
      "history": [                      // every pass, oldest first, all <= asOf
        { "date": "2024-01-16", "areaHa": 33.3, "valid": true }   // valid=false → cloudy/suspect, not used in maths
      ],
      "dryBy":    { "earliest": "2024-04-05", "likely": "2024-04-08", "latest": "2024-04-11" },  // or null
      "daysLeft": { "min": 10, "likely": 13, "max": 16 },                                    // or null
      "shrinkVsNeighbours": 2.33,       // relative shrink rate ÷ median of shrinking ponds within 25 km; or null
      "flag": "faster-than-sun",        // or null
      "status": "critical"              // "dry" | "critical" | "watch" | "ok" | "unknown"
    }
  ],
  "talukas": [                          // optional (only when ponds have a taluka): most urgent first
    { "name": "Udgir", "nameMr": "उदगीर", "ponds": 67, "dry": 0, "critical": 3, "watch": 8, "ok": 50,
      "unknown": 6, "flagged": 3, "earliestLikelyDry": "2026-10-23" }   // earliest dryBy.likely of ponds not yet dry, or null
  ]
}
```

## Field rules

| Field | Type | Notes |
|---|---|---|
| dates | `"YYYY-MM-DD"` string | All ISO dates, no times, no timezones. |
| areas | number, hectares | 1 pixel at 10 m = 0.01 ha. Round to 1–2 decimals. |
| `history` | array | Ascending by date. Includes invalid passes (`valid: false`) so the UI can draw them greyed out. |
| `dryBy` / `daysLeft` | object or `null` | `null` when status is `ok` because the pond is **stable** (not shrinking), or when status is `unknown`. A pond is also `ok`/stable when its shrink is within measurement noise (slope + 2 standard errors ≥ 0) or it would last more than a year; `latest` is capped at 365 days. |
| `dryBy` / `daysLeft` when `dry` | | `daysLeft` = `{min:0, likely:0, max:0}`, `dryBy` = `null`. |
| `confidence`, `confidenceReason` | `"high"`/`"low"`, string or `null` | Only on ponds with a countdown (`dryBy` set). `low` when it rests on just 3 clear passes or one pass carries more than 60% of the drop; low-confidence critical calls were right far less often in every backtest (`docs/data-quality.md`). Show them, but after the trusted ones. |
| `shrinkVsNeighbours` | number or `null` | `null` for dry/unknown ponds, or when the regional median isn't shrinking. ≥ 2 on a pond ≥ 2 ha → `flag: "faster-than-sun"`. |
| `status` | enum | See below. |
| `taluka` / `talukas` | string / array | From OpenStreetMap taluka boundaries bundled with the backend (`backend/jobs/places/<district>-talukas.json`). Counts in `talukas` add up to the ponds that have a taluka; order = most dry + critical, then most watch, then earliest likely dry date. |

## Status

| Status | Rule | Suggested colour |
|---|---|---|
| `dry` | latest area < 5% of max area | grey/black |
| `critical` | likely days left < 30 | red |
| `watch` | 30 ≤ likely days left ≤ 90 | amber |
| `ok` | likely days left > 90, or stable/growing | green/blue |
| `unknown` | fewer than 3 valid passes in the last 45 days | hatched/light grey |

`unknown` is an addition to the brief: it covers ponds hidden by cloud for too long. Never show a countdown for them.

## How the numbers are made (summary)

- **Countdown:** linear fit of valid areas in the 45 days up to `asOf` (needs ≥ 3 points). Days left = (area now − 5% of max) ÷ shrink rate, with the rate scaled by expected ET0 for the next 30 days ÷ ET0 during the fit window. The range comes from the slope ± its standard error, widened to at least ±20%. Code: `backend/logic/countdown.py`.
- **Faster than the sun:** r = −slope ÷ max area. A pond's ratio is r ÷ the median r of the shrinking (non-dry, r > 0) ponds within 25 km (at least 3, else no ratio). Code: `backend/logic/flags.py`.

## API

- `GET /regions` returns `{ "regions": [{ "id", "name", "mode": "replay" | "live", "bbox", "synthetic", "first", "last", "dates": ["YYYY-MM-DD", ...] }], "divisions": [{ "id", "name", "nameMr", "members": [region ids], "first", "last", "dates" }] }`: only regions with published snapshots; `dates` are the exact values the date slider should offer. `divisions` lists divisions that have a summary (`dates` = dated summaries for `GET /division?asOf=`).
- `GET /ponds?region=latur-2024&asOf=YYYY-MM-DD` returns the whole document above.
- `GET /ponds/{id}?region=...&asOf=...` returns one element of `ponds` (same shape), plus `asOf` and `region`.
  Without `asOf` it is the pond's latest state, read from DynamoDB (same fields).
- `POST /plan` with body `{ "region": "latur-2024", "asOf": "YYYY-MM-DD", "language": "en" | "mr" }` returns
  `{ "markdown": "...", "pondIds": ["P003", ...], "source": "template" | "local-ai" | "bedrock", "status": "ready" | "generating" | "template", "asOf": "...", "language": "en" }`.
  The same works for `"region": "marathwada-2026"` (the division plan).
  - `status: "generating"`: you got the instant template plan; the AI plan is being written. Ask again (same body) every ~5 s until `status` is `ready` (give up after ~2 min).
  - `status: "ready"`: the AI version. `source: "local-ai"` (what runs today): the template plan with a `## Briefing` section under
    the title, written by an open model (Qwen3-1.7B) in our Lambda, each sentence checked against the data; `briefing` holds just
    those bullets and `model` names the model. English only (Marathi stays `template`). `source: "bedrock"`: whole plan by Claude on
    Bedrock, behind the number guard (switched on once AWS enables Bedrock).
  - `aiNote`: the AI writer is busy with another plan (one runs at a time); the template is shown, ask again later.
  - `status: "template"`: AI is switched off or failed recently (`aiError` says why); show the template plan.

- `GET /backtest?region=latur-2024` returns the backtest report (`summary.rangeHitRate`, `medianLeadDays`, `criticalPrecision`, `criticalRecall`, per-pond `actualDry` / `firstCritical` / `leadDays`, and `variants.noHeatAdjustment`). `synthetic: true` means the numbers only test the code.

- `GET /alerts?region=latur-2024` returns `{ "region", "name", "simulated": true|false, "events": [{ "asOf", "subject", "alerts": [{ "id", "place", "reason": "critical" | "dry" | "flag", "dryBy", "ratio", "areaNowHa", "maxAreaHa" }], "delivered"? }] }`. Replay regions: what Talaab *would have* emailed pass by pass (`simulated: true`, nothing sent). Live: the alerts actually emailed via Amazon SNS. Each pond is alerted for each reason at most once per season.

- `GET /division?division=marathwada-2026&asOf=YYYY-MM-DD` (both optional) returns the Divisional Commissioner's summary of
  every live district: `{ "division": {"id", "name", "nameMr", "live"}, "asOf", "totals": {"districts", "ponds", "dry",
  "critical", "watch", "ok", "unknown", "flagged", "talukas"}, "districts": [{"region", "name", "nameMr", "asOf", "ponds",
  "dry", "critical", "watch", "ok", "unknown", "flagged", "talukas", "earliestLikelyDry", "change"?}], "change": {...} | null,
  "talukas": [up to 10 talukas with dry/critical/watch ponds, same counts + "district", "region"], "allTalukas": [every taluka
  of every district, same shape], "urgentPonds": [up to 15 pond rows + "region", "district"], "inspect": [up to 10 flagged
  pond rows] }`. Districts and talukas are most-in-need first (dry + critical, then watch, then earliest likely dry date).
  `asOf` returns the latest summary on or before that date. Written by recompute after the districts are recomputed.
  - **What changed since the run before:** each district is compared with its latest snapshot on or before `asOf` − 5 days.
    District `change` = `{"since": that snapshot's date, "dry", "critical", "watch", "unknown", "flagged"}` (differences of
    counts, e.g. `critical: 14` = 14 more critical ponds; negative = fewer). Top-level `change` = the sum over compared
    districts, `{"since": asOf − 5 days, "districts": how many were compared, ...}`; `null` (and no district `change`) when there
    is no earlier snapshot. A big drop in `unknown` means ponds became forecastable, which is often why critical/watch rise:
    show the two together.
  - Pond rows (`urgentPonds`, `inspect`): `{region, district, districtMr, id, place, taluka, talukaMr, status, areaNowHa,
    maxAreaHa, dryBy, daysLeft, flag, shrinkVsNeighbours, lat, lon}`. Open the pond with `GET /ponds/{id}?region={region}`.
- `GET /division/outlines?division=marathwada-2026` returns the district outlines for a division map: a GeoJSON
  FeatureCollection with `properties: {region, name, nameMr}` (join to `GET /division` `districts[].region`) and `credit`
  (show "© OpenStreetMap contributors"). Simplified to ~300 m, ~15 KB gzipped, cached for a day. Static (rebuilt with
  `backend/scripts/build_division_outlines.py`).
- `POST /plan` with `"region": "marathwada-2026"` returns the division plan (same response shape, `status: "template"`, `pondIds: []`).
- `GET /imagery/{region}/index.json`, `.../outlines.geojson`, `.../{pondId}/{YYYY-MM-DD}.jpg`: district imagery (`docs/imagery-contract.md`).

Live districts in a division don't email one by one: their new alerts are queued and ONE digest email goes out per
Marathwada run (end of the `talaab-marathwada` workflow, and the scheduled recompute). `GET /alerts` for a district
still lists what was sent to it, with the digest's subject.

Errors: `{ "error": "message" }` with HTTP 400 (bad params) or 404 (unknown region/pond/asOf).

## Data credits

Sentinel-2 L2A: contains modified Copernicus Sentinel data 2024, via AWS Open Data / Element 84 Earth Search. ET0 and precipitation: Open-Meteo.com (CC BY 4.0). Village names and taluka boundaries: © OpenStreetMap contributors (ODbL).
