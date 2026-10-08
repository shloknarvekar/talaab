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

## Publish

```bash
python backend/scripts/build_snapshots.py data/latur-2024/measurements.json   # -> data/latur-2024/asof/*.json
python backend/scripts/publish_data.py data/latur-2024/asof/                  # -> S3, served by the API
```

Sources: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search), Open-Meteo (CC BY 4.0).
