# From one district to Maharashtra and India: measured run and projection

**Measured:** we ran all of Latur district (7,226 km² from the OSM boundary; the official figure is 7,157 km²) on AWS for the 2024 season.
**Projected:** Maharashtra and India, scaled linearly from that run. Everything below the "Projection" heading is an estimate.

## What ran (measured, 9 Oct 2026)

```
python backend/scripts/run_district.py --wait      # Step Functions talaab-district
```

| | |
|---|---|
| Area | 7,226 km², split into 42 cells of 0.15° (each with a ~1.6 km overlap so no pond is cut) |
| Satellite passes | 26 dates, Jan–Jun 2024, Sentinel-2 L2A < 20% cloud; for each date the tile covering the cell best |
| Ponds | 450 detected → **435 kept**, 15 excluded by the data-quality rules (with reasons) |
| Wall-clock time | **161 s** (8 cells in parallel; slowest cell 37 s; merge 3.5 s; recompute 9 s) |
| Lambda compute | 2,221 GB-s (cells 2 GB × 1,109 s; merge 1 GB × 3.5 s) |
| Cost | **$0.00**: inside the free tier (400,000 GB-s/month). The same run would cost **$0.03** without the free tier. |
| Step Functions | ~170 state transitions (free tier: 4,000/month) |
| Data egress | none: Sentinel-2 COGs are read from the public `sentinel-cogs` bucket in the same region (us-west-2) |

The same cell processed on a laptop took 447 s. On Lambda it took 50 s (the first, cold run) or 26 s on average, because Lambda reads the images inside the same AWS region.

### And live, every 5 days (measured, 9 Oct 2026)

EventBridge Scheduler starts the same state machine for `latur-district-2026` (`end: "today"`, the
season since 1 Sep 2026, scenes up to 45% tile cloud with the per-pond cloud check). First run:
**60 s wall clock, 383 ponds, 6 passes, 573 GB-s** (about $0.008 without the free tier). The run
reprocesses the season so far each time, so the cost grows with the season. At ~30 passes by June it
should be roughly the replay's 2,200 GB-s per run, about 13,000 GB-s per month, still about 3% of
the free tier.

### Do the forecasts still hold at district scale?

Same honest backtest as the validated 0.15° box (`docs/backtest-latur-district-2024.md`). Each as-of date uses only data up to that date.

| | Validated box (13 ponds) | **Whole district (435 ponds)** |
|---|---|---|
| Critical calls that were right (precision) | 55% | **71%** |
| Ponds about to dry that we had marked critical (recall) | 50% | **60%** |
| Median warning before a pond dried | 27.5 days | **25 days** (197 ponds) |
| Median absolute error of the likely date | 23 days | **19 days** |
| Actual dry date inside our range | 48% | **41%** |

259 of the 435 ponds dried during the 2024 season. The method was tuned on a 13-pond box and held up, slightly better, on 435 ponds it had never seen.

## Projection (estimates, linear in area)

Basis: 0.307 GB-s per km² per season, 85 GB-s per satellite pass for the district, 26 s per cell on average, and 0.06 ponds per km² (Latur's density).

| | Latur (measured) | Maharashtra | India |
|---|---|---|---|
| Area | 7,226 km² | 307,713 km² (×42.6) | 3,287,263 km² (×455) |
| Grid cells | 42 | ~1,790 | ~19,100 |
| Ponds (at Latur's density) | 435 | ~18,500 | order of 200,000 (density varies a lot by region) |
| Full-season replay, Lambda | $0.03 | **~$1.26** | **~$13.5** |
| Live month, 6 passes, Lambda* | $0.01 | ~$0.29 | ~$3.1 (233,000 GB-s, *within* the 400,000 GB-s free tier) |
| Step Functions per season run | free | ~7,200 transitions ≈ $0.08 | ~76,000 ≈ $1.80 |
| Wall time, 8 cells in parallel (what we ran; this account allows 10 concurrent Lambdas) | 2.7 min (measured) | ~1.6 h | ~17.5 h |
| Wall time at the standard 1,000-concurrency quota | <1 min | ~1 min | ~8 min |

\*Live-month figures assume each 5-day run processes only the new pass. Today the pipeline reprocesses the whole season window on every run, which is fine for one district. Making it incremental is a small change: store each cell's pond footprints after the reference pass, then measure only new dates.

## What would have to change (honest list)

1. **Concurrency quota.** This new account allows 10 concurrent Lambdas. India-scale needs the standard 1,000 (a quota request), plus a Step Functions *Distributed* Map (up to 10,000 parallel children) instead of the inline Map.
2. **Weather per district.** The merge currently uses one Open-Meteo point (the district centre) for ET0 and rain. A state run needs a point per district, or per cell. Open-Meteo's free tier is for non-commercial use and has daily limits, so a national run would need their paid API or ERA5 from AWS Open Data.
3. **Reference date.** We pick the wettest early pass (16 Jan for Latur). Other regions have different monsoons and dry seasons, so the reference date must be chosen per district.
4. **Faster-than-sun baseline: done.** Each pond is compared with the shrinking ponds within 25 km, not the whole region, so the baseline stays local at any scale. Results on the validated box are unchanged, because the box is smaller than 25 km.
5. **Village names.** One OSM Overpass request covered Latur (2,107 places). A state needs a pre-extracted OSM file (for example the Geofabrik India extract) rather than the public Overpass API.
6. **API and web payload.** `GET /ponds` returns every pond in a region (435 here). A state needs per-district queries or map tiles. The DynamoDB table is already keyed `regionId / pondId`, so a district-per-region layout scales naturally.
7. **Cloud.** Kharif-season monitoring (Jun–Sep) sees few clear passes. Sentinel-1 radar would be the next data source. It is also free on AWS Open Data.

None of these changes the method. They are engineering and quota work.
