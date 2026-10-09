# Talaab (तालाब, "pond"): *The sun drinks first*

[![CI](https://github.com/shloknarvekar/talaab/actions/workflows/ci.yml/badge.svg)](https://github.com/shloknarvekar/talaab/actions/workflows/ci.yml)

Per-pond "dry-by" countdowns and pumping flags for drought districts, built from free Sentinel-2 satellite data on AWS.

> Team **Syntax Errors**, WeMakeDevs x AWS *Environmental Hacks* hackathon (Heat & Water track), Oct 2026.

**Live site: https://main.duvnkrxj02sz1.amplifyapp.com** (AWS Amplify) · API: `https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com`

## The problem

On 25 Sep 2026 Maharashtra declared drought in 265 of its 358 talukas. Every district has to finalise a water-scarcity action plan by 15 Oct, split into Oct–Dec, Jan–Mar and Apr–Jun, and crack down on unauthorised water extraction. Villages depend on small ponds and tanks that shrink all through the dry season. In Latur between January and mid-June 2024, the sun could evaporate about **1 metre** of open water (Open-Meteo ET0 ≈ 974 mm), while only about **43 mm** of rain fell from January to May. Government maps track small ponds only seasonally, and nobody gives a district a countdown for each pond.

## How it works

1. **Find ponds.** Sentinel-2 imagery, free on AWS with a new pass about every 5 days, locates every pond in the district automatically.
2. **Measure.** Each pond's water area is measured on every clear pass, and noisy passes are cleaned out.
3. **Two checks per pond:**
   - **Countdown:** a dry-by date *range* (earliest, likely, latest) from the shrink trend, adjusted for expected heat.
   - **Faster than the sun:** a pond shrinking much faster than its neighbours under the same sun is flagged for inspection (likely pumping).
4. **AI plan.** Amazon Bedrock (Strands Agents) drafts the district's quarterly scarcity plan in English and Marathi, using only our numbers.
5. **Automatic.** The analysis re-runs every 5 days on AWS.

The demo replays **Latur, Jan–Jun 2024** as an honest backtest: each "as of" date uses only the data available up to that date.

**Whole district, on AWS.** All of Latur district (7,157 km², **435 ponds**) runs on AWS Step Functions + Lambda in **161 seconds for $0**, inside the free tier. On those 435 ponds, 71% of critical calls came true and the median warning was 25 days. **And live:** every 5 days EventBridge Scheduler re-runs the whole district for the 2026 season (60 s, 383 ponds, $0) and emails the district officer about ponds that newly need action. Projection to Maharashtra and India, with an honest list of what would change: [`docs/scale-projection.md`](docs/scale-projection.md).

## Honest by design

- **Ranges, not fake dates.** Every pond gets an earliest–likely–latest dry-by range. A pond whose shrinking is within measurement noise is called *stable*; we don't invent a date.
- **Replays can't see the future.** Each as-of snapshot is built only from satellite passes and weather available on that day, so the 2024 replay is a real backtest.
- **Validated on an unseen season.** All rules were built on 2024; on the held-out 2023 season Talaab still flagged 62% of ponds about to dry in time (25-day median warning, 66% of critical calls right). See [`docs/model-experiment.md`](docs/model-experiment.md).
- **Proof, not claims.** [`docs/backtest-*.md`](docs/) scores every past prediction against what actually happened: dry dates inside our range, days of warning, false and missed alarms. It also runs with the heat adjustment switched off for comparison.
- **The AI can't invent numbers.** The Bedrock plan writer only sees our data through two tools, and a *number guard* rejects any draft containing a number that isn't in the data.
- **It tells you; you don't have to check.** After each 5-day recompute, Amazon SNS emails the district officer about ponds that *newly* turned critical, dried up, or started shrinking faster than the sun. There are no repeats, and every number comes from the snapshot.
- **Officials' language and structure.** Plans come in English and Marathi, with one section per scarcity period (Oct–Dec, Jan–Mar, Apr–Jun) as the state order requires, a table by village and a concrete action per pond.

## Architecture (AWS, us-west-2)

Full diagram and flow: **[docs/architecture.md](docs/architecture.md)**.

| AWS service | Role |
|---|---|
| **S3** | Pipeline measurements, per-date snapshots, cached plans, backtest |
| **Lambda** (×7) | `pipeline-grid` + `pipeline-cell` + `pipeline-merge` (satellite pipeline), `api`, `recompute`, `plan-worker` (Strands Agents), `hello` |
| **Step Functions** | `talaab-district`: grid → one Lambda per 0.15° cell (42 for Latur, 8 in parallel) → merge; started every 5 days for the live district |
| **API Gateway** (HTTP API) | Public API, throttled |
| **EventBridge Scheduler** | Every 5 days (one Sentinel-2 revisit): re-measure the live district from satellite, and recompute every region |
| **DynamoDB** | Latest state of every pond |
| **Amazon SNS** | Emails the district officer when a pond newly turns critical, dries up, or is flagged faster than the sun |
| **Amazon Bedrock** | Claude writes the plan in English and Marathi (behind the number guard) |
| **CloudWatch** | Logs plus the `talaab-ops` dashboard |
| **Amplify Hosting** | The web map |
| **AWS Open Data** | Sentinel-2 L2A imagery, read straight from S3 |

## Repo layout

| Folder | What |
|---|---|
| `pipeline/` | Satellite pipeline: STAC search, water mask, pond detection, cleanup, evaporation |
| `backend/` | Countdown, flags, snapshots, backtest (`logic/`), API (`api/`), recompute job (`jobs/`), plan agent (`agent/`), SAM template, scripts, 65 tests |
| `web/` | Vite + React + Leaflet map |
| `data/` | Measurements and snapshots per region (`latur-2024`, `latur-2026`, `latur-2024-synthetic` test data) |
| `docs/` | Data contract, demo script, architecture, sources |

## Live API (AWS, us-west-2)

Base URL: `https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com`

| Call | Returns |
|---|---|
| `GET /regions` | Regions with data (2024 replay, live 2026, synthetic test data) and the exact dates available |
| `GET /ponds?region=latur-2024&asOf=2024-03-26` | Full `ponds.json` ([contract](docs/data-contract.md)); `asOf` resolves to the latest snapshot on or before that date |
| `GET /ponds/P003?region=latur-2024&asOf=2024-03-26` | One pond |
| `POST /plan` `{"region":"latur-2024","asOf":"2024-03-26","language":"mr"}` | `{markdown, pondIds, source, status}`. Instant template plan; the Bedrock plan arrives on a later call (`status: ready`) |
| `GET /backtest?region=latur-2024` | How well past predictions matched reality |

```bash
curl "https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com/regions"
python backend/scripts/smoke_test.py   # checks every endpoint
```

## Setup

```bash
# backend tests (pure Python, no AWS needed)
pip install -r backend/requirements-dev.txt
cd backend && python -m pytest

# deploy (needs AWS CLI + SAM CLI + credentials)
cd backend && sam build && sam deploy

# AI plan writer (Strands Agents on Bedrock): build the layer, then deploy with AI on/off
python backend/scripts/build_layer.py        # needs `pip install uv`; no Docker
cd backend && sam build && sam deploy --parameter-overrides PlanAI=on   # PlanAI=off = template only, no Bedrock cost

# publish pipeline output: checks it, uploads measurements.json and recomputes that region on AWS
pip install -r backend/scripts/requirements.txt
python backend/scripts/check_measurements.py data/latur-2024/measurements.json
python backend/scripts/upload_measurements.py data/latur-2024/measurements.json

# whole district on AWS: build the pipeline layer + function, deploy, then run (Step Functions)
python backend/scripts/build_layer.py --name pipeline-layer
python backend/scripts/stage_pipeline_fn.py
python backend/scripts/run_district.py --wait                               # 2024 replay
python backend/scripts/run_district.py --region latur-district-2026 --wait  # live season (what the schedule runs)

# backtest report (docs/backtest-<region>.md + GET /backtest)
python backend/scripts/run_backtest.py data/latur-2024/measurements.json --upload

# publish the web map on AWS Amplify (builds web/, uploads, prints the URL)
python backend/scripts/deploy_web.py

# tear everything down after judging
cd backend && sam delete
```

## Data credits

- **Sentinel-2 L2A**: contains modified Copernicus Sentinel data 2024, accessed via the [AWS Open Data Registry](https://registry.opendata.aws/sentinel-2-l2a-cogs/) and the Element 84 Earth Search STAC API.
- **Open-Meteo**: weather data (ET0, precipitation) from [Open-Meteo.com](https://open-meteo.com/), licensed CC BY 4.0.
- **OpenStreetMap**: village names for each pond (and the map basemap): © OpenStreetMap contributors, ODbL 1.0.
- **Pond thumbnails and outlines** in the web app are cut from the same Sentinel-2 L2A true-colour images (`pipeline/imagery.py`).
- **Optional basemaps**: CARTO Dark Matter (only with `VITE_CARTO_API_KEY`) and the Esri World Imagery satellite layer (Esri, Maxar, Earthstar Geographics).

## AI tools used

- **Claude Code** (Anthropic): backend logic and tests, AWS SAM templates, scripts, docs (pair-programmed with the team).
- **Amazon Bedrock** (Claude) via **Strands Agents SDK**: in-product plan writer.
- _Add any others the team uses._

## License

MIT, see [LICENSE](LICENSE).
