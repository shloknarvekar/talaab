# Pipeline output contract: `measurements.json`

**Who writes it:** the satellite pipeline (`pipeline/`, Coder 1).
**Who reads it:** the backend snapshot builder (`backend/logic/snapshot.py`), which turns it into one
`ponds.json` snapshot per as-of date ([data contract](data-contract.md)).

The pipeline only **measures** (water area per pond per pass, plus ET0). All the maths for
countdowns, flags and status lives in the backend, in one tested place. Snapshots for any as-of
date are computed from this file using only data dated on or before that date.

## Shape

```jsonc
{
  "region": { "id": "latur-2024", "name": "Latur (2024 replay)", "bbox": [76.47, 18.33, 76.62, 18.48] },
  "generatedAt": "2026-10-09T10:00:00Z",
  "referenceDate": "2024-01-16",                 // pass used to detect ponds
  "scenes": [                                     // every pass considered, oldest first
    { "date": "2024-01-16", "id": "S2B_43QFA_20240116_0_L2A", "status": "ok" }   // "ok" | "suspect"
  ],
  "et0": [                                        // observed daily values (Open-Meteo archive), oldest first
    { "date": "2024-01-16", "et0": 4.1, "precip": 0.0 }   // mm/day
  ],
  "et0Climatology": { "01-16": 4.0, "01-17": 4.1 },  // "MM-DD" -> mean ET0 2019-2023 (mm/day), all 365/366 days
  "et0Forecast": [ { "date": "2026-10-10", "et0": 5.2 } ],  // optional, live mode only (Open-Meteo forecast)
  "ponds": [
    {
      "id": "P001",                               // sorted by refAreaHa, largest first
      "lat": 18.4512, "lon": 76.5031,             // centroid, WGS84
      "place": "near <village>",                  // free text (OSM if used)
      "refAreaHa": 92.4,                          // area on the reference date
      "history": [                                // one entry per scene, same dates as `scenes`
        { "date": "2024-01-16", "areaHa": 92.4, "valid": true }   // valid=false: cloud/shadow >20% of footprint, or cleanup drop
      ]
    }
  ]
}
```

## Rules

- Dates are `YYYY-MM-DD`. Areas are in hectares (1 pixel at 10 m = 0.01 ha).
- `history` includes invalid passes with `valid: false` (the map greys them out). Only valid
  points are used in the maths.
- Cleanup belongs to the pipeline: mark the pond pass invalid on SCL cloud, mark the scene
  `suspect` on a region-wide jump, and set `valid: false` on spikes.
- `et0` must cover at least the 45 days before the first as-of date you want, up to the last scene.
- "Expected heat" for the next 30 days comes from `et0Forecast` when present (live), otherwise
  from `et0Climatology` (replay, so it uses only what was knowable in advance).

## Regions and files

| Region id | What | File to produce |
|---|---|---|
| `latur-2024` | 2024 drought replay (Jan–Jun 2024 passes) | `data/latur-2024/measurements.json` |
| `latur-2026` | Live: this season (passes since the monsoon ended, Sep–Oct 2026 onward) | `data/latur-2026/measurements.json` |

Same code, different dates. For `latur-2026` you may leave `et0`, `et0Climatology` and
`et0Forecast` empty: the recompute job fetches recent and forecast weather from Open-Meteo itself.

## Publish (one command)

```bash
python backend/scripts/upload_measurements.py data/latur-2024/measurements.json
```

This uploads to S3 and runs the recompute Lambda straight away: it builds a snapshot for every
pass (plus today for the live region), updates the DynamoDB table and prints a summary. The
same job also runs on its own every 5 days (EventBridge Scheduler).

Sources: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search), Open-Meteo (CC BY 4.0).
