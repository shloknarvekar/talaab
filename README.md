# Talaab (तालाब, "pond"): *The sun drinks first*

Per-pond "dry-by" countdowns and pumping flags for drought districts, built from free Sentinel-2 satellite data on AWS.

> Team **Syntax Errors**, WeMakeDevs x AWS *Environmental Hacks* hackathon (Heat & Water track), Oct 2026.

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

## Architecture (AWS, us-west-2)

_Diagram: TODO in `docs/`._

- **Recompute job** (Lambda, EventBridge Scheduler every 5 days): pipeline measurements in S3 → countdowns and flags for every pass → snapshots in S3 + latest pond state in DynamoDB. The live region also pulls observed and forecast heat from Open-Meteo.
- **API** (Lambda + API Gateway HTTP API): `/ponds`, `/ponds/{id}`, `/plan`.
- **Plan writer**: deterministic EN/MR template, plus a Strands Agents plan on Amazon Bedrock (async worker Lambda, number guard, cached in S3).
- **Web** (Amplify Hosting), **logs** (CloudWatch).

## Repo layout

| Folder | What |
|---|---|
| `pipeline/` | Satellite pipeline: STAC search, water mask, pond detection, cleanup, evaporation |
| `backend/` | Countdown and flag logic, API Lambda, plan agent, SAM template |
| `web/` | Vite + React + Leaflet map |
| `data/latur-2024/` | Generated outputs committed for the demo |
| `docs/` | Data contract, demo script, architecture, sources |

## Live API (AWS, us-west-2)

Base URL: `https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com` (currently serving the mock snapshot until real pipeline data lands)

| Call | Returns |
|---|---|
| `GET /ponds?region=latur-2024&asOf=2024-03-26` | Full `ponds.json` ([contract](docs/data-contract.md)); `asOf` resolves to the latest snapshot on or before that date |
| `GET /ponds/P003?region=latur-2024&asOf=2024-03-26` | One pond |
| `POST /plan` `{"region":"latur-2024","asOf":"2024-03-26","language":"en"}` | `{markdown, pondIds, source, status}`; `language` is `en` or `mr`. Instant template plan; the Bedrock plan arrives on a later call (`status: ready`) |

```bash
curl "https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com/ponds?region=latur-2024"
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

# publish pipeline output: uploads measurements.json and recomputes that region on AWS
pip install -r backend/scripts/requirements.txt
python backend/scripts/upload_measurements.py data/latur-2024/measurements.json
```

## Data credits

- **Sentinel-2 L2A**: contains modified Copernicus Sentinel data 2024, accessed via the [AWS Open Data Registry](https://registry.opendata.aws/sentinel-2-l2a-cogs/) and the Element 84 Earth Search STAC API.
- **Open-Meteo**: weather data (ET0, precipitation) from [Open-Meteo.com](https://open-meteo.com/), licensed CC BY 4.0.
- **OpenStreetMap** (if used for place names and basemap): © OpenStreetMap contributors, ODbL.

## AI tools used

- **Claude Code** (Anthropic): scaffolding, logic and tests, AWS templates.
- **Amazon Bedrock** (Claude) via **Strands Agents SDK**: in-product plan writer.
- _Add any others the team uses._

## License

MIT, see [LICENSE](LICENSE).
