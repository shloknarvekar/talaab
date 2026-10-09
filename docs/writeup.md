# Talaab (तालाब): the sun drinks first

**Per-pond "dry-by" countdowns and pumping alerts for drought districts, from free satellite data on AWS.**

Team **Syntax Errors**: Shlok (backend & AWS), Nikhil (satellite pipeline), Ranit (web), Bhavesh (story & submission)
Live: https://main.duvnkrxj02sz1.amplifyapp.com · Code: https://github.com/shloknarvekar/talaab · Track: Heat & Water

> **[Bhavesh: open with a short human hook, 2–3 sentences: a village in Latur, a water tanker that arrives a week too late. Keep the facts below unchanged.]**

---

## The problem

On 25 September 2026, Maharashtra declared drought in **265 of its 358 talukas**. Every district has
to finalise a water-scarcity action plan by 15 October, with separate plans for **Oct–Dec, Jan–Mar
and Apr–Jun**, and act against unauthorised water extraction.

In the dry season, villages depend on small ponds and tanks that shrink every week. In Latur, from 1
January to 15 June 2024 the sun could evaporate about **0.9 m of open water** (901 mm of reference
evaporation, Open-Meteo), while only **43.5 mm of rain** fell from January to May. Officials see
these ponds in seasonal maps at best. Nobody tells a district **which pond will run dry, and when**.

## What Talaab does

1. **Finds every pond automatically** in free Sentinel-2 imagery (a new pass about every 5 days), read straight from AWS Open Data.
2. **Measures each pond's water area** on every clear pass, and throws out cloudy, broken or implausible readings with stated reasons.
3. **Gives each pond a countdown** as a *range* ("likely dry 16 Oct, between 13 and 23 Oct"), adjusted for the heat expected in the coming month.
4. **Catches ponds shrinking "faster than the sun"**: much faster than nearby ponds under the same weather, which suggests pumping. They're flagged for inspection, never accused.
5. **Writes the district plan** in **English and Marathi**, structured exactly like the state order (one section per scarcity period, a table by village, an action for every pond).
6. **Tells officials when something changes.** Every 5 days AWS recomputes everything, and an email goes out for any pond that *newly* turned critical, dried up or started shrinking faster than the sun.

It runs two ways: **live** on Latur this season, and as an **honest replay of the 2024 drought**, where
every date shows only what Talaab could have known that day.

## Does it work? We checked every forecast

A forecast is only useful if it's right, so we **replayed whole dry seasons**. For every satellite pass
we rebuilt Talaab's forecast using only the data available that day, then compared it with what
actually happened.

| | **Latur 2024** (rules built on this) | **Latur 2023** (never seen: held out) |
|---|---|---|
| Ponds about to dry (≤ 30 days) that Talaab had marked **critical** | **61%** | **62%** |
| "Critical" calls that came true within 30 days | **61%** | **70%** |
| Median warning before a pond dried | **27.5 days** | **25 days** |
| Ponds that dried during the season | 6 of 12 | 13 of 19 |

- **Validated on an unseen season.** Every rule and model choice was made on 2024. Latur 2023 was
  processed afterwards as a final exam, and the results held.
- **Validated on the whole district.** We then ran all **7,157 km² of Latur district** on AWS:
  42 grid cells, **435 ponds**, done in **161 seconds** for **$0** (inside the free tier, and $0.03
  without it). On 435 ponds the rules had never seen, 71% of critical calls came true, 60% of ponds
  about to dry were caught in time, and the median warning was 25 days (197 ponds warned in advance).
  See `docs/scale-projection.md`.
- **And it runs live.** Every 5 days EventBridge Scheduler starts the same state machine for the
  2026 season: the whole district is re-measured from the newest Sentinel-2 passes in about 60 s, and
  new critical, dry or flagged ponds are emailed. The first live run (9 Oct 2026) measured 383 ponds;
  most are honestly "too early to forecast" this soon after the monsoon.
- **What an officer would have received in 2024:** on **5 April**, an alert that ponds P002 and P006
  had turned critical. P006 was dry on the 30 April pass and P002 on the 5 May pass, giving 25 and
  30 days to arrange tankers. Over the whole season Talaab would have sent **9 emails** and never
  repeated one.

## Honest by design

We treated honesty as a feature, because district officials will only use a tool they can trust.

- **Ranges, never fake precision.** A pond whose shrinking is within measurement noise is called
  *stable*, not given a date. Early in the season, with too few clear passes, a pond is "too early
  to forecast".
- **We fixed the data, not the score.** The first real backtest was weak (only 32% of ponds about to
  dry flagged in time). Pond by pond, we found a broken satellite pass that hit every pond, readings
  the cleanup ignored, four "ponds" that were never there and one signal that couldn't be water. We
  wrote physical rules for each, kept only the real ponds, and the share flagged in time rose to
  **61%**, while synthetic results stayed the same, so we weren't gaming the score. Full story:
  `docs/data-quality.md`.
- **We pre-registered our experiments.** To fix over-pessimism on big tanks we tested shape-aware
  models with a decision rule committed to git *before* the run. They didn't beat the current model
  on the unseen season, so we kept it and **published the negative result** (`docs/model-experiment.md`).
- **The AI can't invent numbers.** The plan writer (Claude on Amazon Bedrock, via Strands Agents)
  sees our data only through two tools locked to one date, and a **number guard** rejects any draft
  containing a number that isn't in the data. Without it, Talaab still produces a deterministic plan.
- **Known limits, stated plainly.** Big tanks are often predicted to dry too early (9 times in 2024).
  Passes are about 5 days apart, so a dry date is known only to within a window. The heat
  adjustment helped clearly in 2024 (median error 18 vs 33 days) but made little difference in 2023.
  12–19 ponds per season is a small sample.

## Built on AWS

Everything is serverless in **us-west-2** (the same region as the Sentinel-2 open data), deployed from
one SAM template, with **no hourly cost while idle**.

| AWS service | What it does in Talaab |
|---|---|
| **AWS Open Data** (Sentinel-2 L2A COGs on S3) | The satellite imagery: windows read directly over HTTPS, no downloads |
| **AWS Lambda** (7 functions) | `pipeline-grid` (lists the district's grid cells), `pipeline-cell` (finds and measures the ponds in one grid cell from Sentinel-2), `pipeline-merge` (joins the cells, applies the quality rules, adds weather), `api` (the website's API), `recompute` (countdowns, flags, snapshots, alerts), `plan-worker` (AI plan), `hello` |
| **AWS Step Functions** | `talaab-district`: fans a whole district out to one Lambda per 0.15° cell (42 for Latur, 8 in parallel, with retries), then merges. Latur district takes 161 s. |
| **Amazon API Gateway** (HTTP API) | Public API: `/regions`, `/ponds`, `/plan`, `/backtest`, `/alerts`; throttled, CORS limited to our site |
| **Amazon EventBridge Scheduler** | Every 5 days, matching the satellite revisit: re-measures the live district from Sentinel-2 (Step Functions) and recomputes every region |
| **Amazon S3** | Measurements, a snapshot per date, cached plans, backtests, alert history |
| **Amazon DynamoDB** | Latest state of every pond |
| **Amazon SNS** | Email alerts to the district officer (only new changes) |
| **Amazon Bedrock + Strands Agents** | Claude writes the plan in English and Marathi behind the number guard. *Fully built and tested; switched on once AWS approves our new account's model quota.* |
| **Amazon CloudWatch** | One log line per action, plus the `talaab-ops` dashboard |
| **AWS Amplify Hosting** | The web map |

Data flow: Step Functions → one `pipeline-cell` Lambda per cell (reads Sentinel-2 in-region) → `pipeline-merge` → `measurements.json` → S3 → recompute Lambda (every 5 days or on upload) → a
snapshot per date in S3 + DynamoDB + SNS alerts → API → website. Diagram: `docs/architecture.md`.

## How it's built

- **Satellite pipeline (Python):** STAC search on Element 84 Earth Search; NDWI water masks with
  Sentinel-2 scene-classification cloud masking; connected-component pond detection; per-pass area;
  quality rules (suspect passes both ways, spikes and dips, pond existence, implausible rises).
- **Forecasting (Python, deterministic):** a robust Theil–Sen trend over the last 45 days (at least
  3 clear passes spanning 15 days); days to reach 5% of the pond's maximum area, scaled by expected
  vs recent evaporation; range from the slope's standard error (at least ±20%). The "faster than
  the sun" flag compares each pond's relative shrink rate with the median of the ponds within
  25 km that are actually shrinking.
- **Plans:** a deterministic English/Marathi plan, plus the AI version, cached so each date and
  language is paid for once.
- **Web:** Vite + React + Leaflet + Recharts; the browser does no maths and only shows what the API says.
- **Quality:** 80 backend tests and 23 pipeline tests, a live smoke test of every endpoint, honest
  backtests, and an ablation script that reproduces every before/after number.

## Challenges we hit

- **A brand-new AWS account had Bedrock quotas of 0.** We built the AI path end to end anyway (and
  tested it up to the Bedrock call), made the plan work without AI, and opened a support case.
- **Real satellite data is messy.** Our first honest backtest was weak; the fix was understanding
  the data, not tuning the model.
- **No Docker on the laptop.** We packaged the Strands Agents Lambda layer for Linux ARM from Windows
  using `uv`. The satellite step (rasterio/GDAL) later moved onto Lambda the same way, after two
  surprises: GDAL needs a system library (`libexpat`) that Lambda's image lacks, so we bundle a
  pinned, checksum-verified copy; and the 250 MB layer limit forced us to trim unused SciPy parts
  carefully. One cell takes 447 s on a laptop and 26–50 s on Lambda next to the imagery.
- **A district is many satellite tiles.** Each 0.15° cell picks, for every date, the image that
  covers it best, and reads it onto one fixed 10 m grid, so a pond lines up across dates. Each cell
  owns only the ponds whose centre is in its core, which removes duplicates at cell edges.
- **Post-monsoon live data:** only a few clear passes, and receding floodwater looks like a pond
  drying, so we added a "too early to forecast" state instead of guessing.

## What's next

- Every district in Maharashtra, then India. Projected from the measured Latur run
  (`docs/scale-projection.md`): Maharashtra is about 1,790 cells and roughly 18,500 ponds, about $1.30
  of Lambda per full season. India is about 19,100 cells, about $13.50 per season and about 8 minutes
  at the standard Lambda concurrency. The work left is engineering and quotas (Distributed Map, weather
  per district, local baselines), not the method.
- Pond depth (from a terrain model or past drought years) for better big-tank forecasts.
- SMS alerts in Marathi to sarpanches, and a WhatsApp summary for district officers.
- A field app for inspectors to confirm or dismiss "faster than the sun" flags, feeding back into the model.

## Data and credits

- **Sentinel-2 L2A**: contains modified Copernicus Sentinel data 2023, 2024 and 2026, via the AWS Open Data Registry and the Element 84 Earth Search STAC API.
- **Open-Meteo** weather (ET0, rain): CC BY 4.0.
- **OpenStreetMap** village names and basemap: © OpenStreetMap contributors, ODbL.

## AI tools we used

- **Claude Code** (Anthropic): backend logic and tests, AWS SAM templates and scripts, data-quality analysis, integration, documentation.
- **[Nikhil: confirm which AI assistant(s) you used for the pipeline.]**
- **[Ranit: confirm which AI assistant(s) you used for the web app.]**
- **In the product:** Claude on **Amazon Bedrock** via the **Strands Agents SDK** writes the plans (behind the number guard).
