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
      "place": "near <village>",        // human label; free text
      "maxAreaHa": 33.3,                // max valid area seen up to asOf (ha)
      "areaNowHa": 8.6,                 // latest valid area up to asOf (ha)
      "history": [                      // every pass, oldest first, all <= asOf
        { "date": "2024-01-16", "areaHa": 33.3, "valid": true }   // valid=false → cloudy/suspect, not used in maths
      ],
      "dryBy":    { "earliest": "2024-04-05", "likely": "2024-04-08", "latest": "2024-04-11" },  // or null
      "daysLeft": { "min": 10, "likely": 13, "max": 16 },                                    // or null
      "shrinkVsNeighbours": 2.33,       // this pond's relative shrink rate ÷ regional median; or null
      "flag": "faster-than-sun",        // or null
      "status": "critical"              // "dry" | "critical" | "watch" | "ok" | "unknown"
    }
  ]
}
```

## Field rules

| Field | Type | Notes |
|---|---|---|
| dates | `"YYYY-MM-DD"` string | All ISO dates, no times, no timezones. |
| areas | number, hectares | 1 pixel at 10 m = 0.01 ha. Round to 1–2 decimals. |
| `history` | array | Ascending by date. Includes invalid passes (`valid: false`) so the UI can draw them greyed out. |
| `dryBy` / `daysLeft` | object or `null` | `null` when status is `ok` because the pond is **stable** (not shrinking), or when status is `unknown`. Values are capped at 365 days, so 365 means "a year or more". |
| `dryBy` / `daysLeft` when `dry` | | `daysLeft` = `{min:0, likely:0, max:0}`, `dryBy` = `null`. |
| `shrinkVsNeighbours` | number or `null` | `null` for dry/unknown ponds, or when the regional median isn't shrinking. ≥ 2 on a pond ≥ 2 ha → `flag: "faster-than-sun"`. |
| `status` | enum | See below. |

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
- **Faster than the sun:** r = −slope ÷ max area. A pond's ratio is r ÷ the median r of all non-dry ponds in the region. Code: `backend/logic/flags.py`.

## API

- `GET /ponds?region=latur-2024&asOf=YYYY-MM-DD` returns the whole document above.
- `GET /ponds/{id}?region=...&asOf=...` returns one element of `ponds` (same shape).
- `POST /plan` with body `{ "region": "latur-2024", "asOf": "YYYY-MM-DD", "language": "en" | "mr" }` returns
  `{ "markdown": "...", "pondIds": ["P003", ...], "source": "template" | "bedrock", "status": "ready" | "generating" | "template", "asOf": "...", "language": "en" }`.
  - `status: "generating"`: you got the instant template plan; the AI plan is being written. Ask again (same body) every ~5 s until `status` is `ready` (give up after ~2 min).
  - `status: "ready"`: `source` is `bedrock`; the AI plan passed the number guard (every number in it exists in the data).
  - `status: "template"`: AI is switched off or failed recently (`aiError` says why); show the template plan.

Errors: `{ "error": "message" }` with HTTP 400 (bad params) or 404 (unknown region/pond/asOf).

## Data credits

Sentinel-2 L2A: contains modified Copernicus Sentinel data 2024, via AWS Open Data / Element 84 Earth Search. ET0 and precipitation: Open-Meteo.com (CC BY 4.0).
