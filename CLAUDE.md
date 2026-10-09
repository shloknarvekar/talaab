# CLAUDE.md: shared context for every teammate's AI assistant

We are team "Syntax Errors" in the WeMakeDevs x AWS "Environmental Hacks" hackathon (Heat & Water track). The hackathon started Thu 8 Oct 2026; submissions close Sun 11 Oct 2026, 8:00 PM IST. Judges score: Idea & Impact, Built on AWS, Design & usability, Execution, Demo video (3 min, YouTube). Only the repo + video + writeup are judged.

## RULES WE MUST FOLLOW
- This is a brand-new project started today. Write all code fresh in this repo. Commit small and often.
- AWS must be visibly used (and shown in the video).
- Keep a list of AI tools used (Claude Code etc.) for the README/writeup.
- Credit all data: Sentinel-2 (Copernicus, via AWS Open Data / Element84 Earth Search), Open-Meteo (CC BY 4.0), OpenStreetMap if used.
- Never commit secrets. Use .gitignore and environment variables.
- ZERO SPEND: AWS must stay within free tier + promotional credits (no personal money). Serverless/on-demand only. Never create anything with an idle hourly cost (NAT Gateway, EC2, RDS, OpenSearch, Elastic IP, provisioned DynamoDB/Lambda concurrency, Bedrock provisioned throughput, KMS customer keys). State the expected cost before creating any new AWS resource. Keep Bedrock calls few and small; cache generated plans in S3 instead of regenerating.

## DECISIONS SINCE KICKOFF (read first; these override the brief below)
- **Pipeline output is `measurements.json`, not `ponds.json`.** Spec: `docs/measurements-contract.md`.
  The pipeline only MEASURES (ponds + water area per pass + ET0). The backend computes countdowns,
  flags and status (`backend/logic/`) and builds one `ponds.json` snapshot per as-of date. Do not
  re-implement countdown/flag maths in `pipeline/`.
- Check a file: `python backend/scripts/check_measurements.py data/latur-2024/measurements.json`
  (no AWS needed). Example of a valid file: `data/latur-2024-synthetic/measurements.json`.
- Regions: `latur-2024` (2024 replay, Jan–Jun 2024) and `latur-2026` (LIVE, passes since the 2026
  monsoon; weather is fetched by the backend). `latur-2024-synthetic` is fake test data, labelled so.
- Satellite step runs on a laptop; the result is committed to the repo and uploaded with
  `backend/scripts/upload_measurements.py` (Shlok). AWS recomputes every 5 days (EventBridge Scheduler).
- Live API: https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com — `GET /regions`, `GET /ponds`,
  `GET /ponds/{id}`, `POST /plan` (poll while `status` is `generating`), `GET /backtest`. Details in
  `docs/data-contract.md`.
- Bedrock is wired but OFF until AWS lifts a new-account quota; `/plan` serves the deterministic EN/MR plan.
- Status values include `unknown` (too few clear passes). Stable ponds (incl. shrink within noise) have
  `dryBy: null`.
- Data quality (see `docs/data-quality.md`): suspect passes are judged both ways and their readings are not used;
  single-pass spikes AND dips are dropped; detections that were never real ponds or whose signal is not water level
  are excluded with a reason (`excludedPonds`). Countdown uses a robust Theil–Sen fit and needs 3 passes over 15 days.
- Faster-than-sun baseline = median rate of SHRINKING ponds within 25 km (needs >= 3); stable tanks no longer inflate ratios. The 0.15 deg box fits inside 25 km, so box results are unchanged; at district scale the baseline is local.
- Alerts: SNS topic `talaab-alerts`; recompute emails NEW critical/dry/flagged ponds for live regions only (state in
  `data/{region}/alerts/state.json`, keyed by location). Subscribe with `aws sns subscribe` (emails never in the repo).
- District scale: region `latur-district-2024` (whole district, 435 ponds) is produced ON AWS by Step Functions
  `talaab-district` (`backend/scripts/run_district.py`): `pipeline/district.py` grid (0.15 deg cells + overlap,
  OSM boundary) -> `pipeline/cell.py` per cell (Lambda `pipeline-cell`) -> `pipeline_lambda/merge_handler.py`.
  Layer: `build_layer.py --name pipeline-layer` (vendors libexpat; keep under 250 MB). Projection: `docs/scale-projection.md`.
- Web (`web/`): always uses the live API (`VITE_TALAAB_API_URL` overrides); opens on the live region; tabs Ponds /
  Plan / Accuracy. No countdown maths in the browser.

=== PROJECT BRIEF: TALAAB (तालाब, "pond") — "The sun drinks first" ===

## PROBLEM
Maharashtra declared drought in 265 of 358 talukas on 25 Sep 2026. The Water Supply Minister ordered every district to finalise its water-scarcity action plan by 15 Oct, with separate plans for Oct–Dec, Jan–Mar and Apr–Jun, based on projected shortages, plus a crackdown on unauthorised water extraction. Villages depend on small ponds and tanks that shrink all dry season; in Latur from Jan to mid-June 2024 the sun could evaporate ~1 metre of water off open water (Open-Meteo ET0 ≈ 974 mm) while only ~43 mm of rain fell Jan–May. Government satellite maps track small ponds only seasonally. Nobody gives a district a per-pond countdown.

## WHAT TALAAB DOES (one flow)
1. Satellite finds every pond in a district automatically (Sentinel-2, free on AWS, a new pass every ~5 days).
2. Measures each pond's water area on every clear pass; cleans noisy passes.
3. Two checks per pond:
   a. Countdown: a "dry-by" date RANGE (earliest / likely / latest) from the shrink trend, adjusted for upcoming heat (evaporation).
   b. "Faster than the sun": a pond shrinking much faster than similar ponds nearby, under the same sun, is flagged for inspection (likely pumping).
4. AI drafts the district's quarterly scarcity plan (which villages/ponds need action in which period, which ponds to inspect), in English and Marathi, using ONLY numbers from our data.
5. Re-runs automatically every 5 days on AWS.

Demo region: Latur, Maharashtra, replaying Jan–Jun 2024 (a real drought year). Use an "as of" date so we can show honest backtests: the countdown at a given date uses only data up to that date.

## DESIGN PRINCIPLES
- Deterministic maths stays deterministic (water detection, trends, flags). AI only cleans up ambiguous inputs and writes the plan.
- Always show ranges, never a fake-precise date. Label the 2024 replay clearly.
- No login, no mobile app, one district done well.

## DATA SOURCES (no keys needed)
- STAC API: https://earth-search.aws.element84.com/v1, collection "sentinel-2-l2a". Assets: "green" (B03, 10 m), "nir" (B08, 10 m), "scl" (scene classification, 20 m), "visual" (true colour). Images are COGs in S3 bucket sentinel-cogs (us-west-2); read windows over HTTPS with rasterio. Set AWS_NO_SIGN_REQUEST=YES and GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR. Filter eo:cloud_cover < 10.
- Latur test box (lon/lat): [76.47, 18.33, 76.62, 18.48] (tile 43QFA). Jan–May 2024 has ~24 near-cloud-free passes.
- Evaporation: Open-Meteo daily et0_fao_evapotranspiration + precipitation_sum.
  - Past/replay: https://archive-api.open-meteo.com/v1/archive
  - Forecast (live): https://api.open-meteo.com/v1/forecast (forecast_days=16)
  - "Expected" heat for replay = average of the same calendar window over 2019–2023 (what we would have known in advance; no peeking at the future).

## METHOD (keep it simple)
- Water mask: NDWI = (green − nir)/(green + nir); water if NDWI > 0.05 (tunable).
- Pond detection: on the reference date (wettest early pass, e.g. 2024-01-16), label connected water pixels; keep components of 1–200 ha (100–20,000 px at 10 m). Each pond's footprint = component dilated by 2 px. Pond ids P001, P002… sorted by area.
- Area per pass: water pixels inside the footprint × 0.01 ha.
- Cleanup: mark a pass invalid for a pond if >20% of its footprint is cloud/shadow/no-data in SCL (classes 0,1,3,8,9,10). Mark a whole pass "suspect" if total water area in the box jumps >40% vs neighbouring passes with no rain in between. Drop single-point spikes (area up >50% then back down) unless rain explains it.
- Countdown (as of date T): use valid points in the last 45 days (≥3 points). Linear fit of area vs time. If slope ≥ 0 → "stable". Else days to reach 5% of max area = (A_now − 0.05·A_max)/|slope|, with the slope scaled by (expected mean ET0 for the next 30 days ÷ mean ET0 in the fit window). Range: earliest/latest from slope ± its standard error, at least ±20%.
- Faster-than-sun flag: relative shrink rate r = −slope / A_ref per day. Compare each pond to the median r of all non-dry ponds in the region over the same window. Flag if ratio ≥ 2 and A_ref ≥ 2 ha. Also report the region's ET0 total for that window as "the sun's share".
- Status: dry (area < 5% of max), critical (likely < 30 days), watch (30–90), ok (> 90 or stable).

## DATA CONTRACT: ponds.json (everyone builds against this)
Full spec: `docs/data-contract.md`. Mock: `web/public/mock/ponds.json`.
```
{
  "region": {"id": "latur-2024", "name": "Latur (2024 replay)", "bbox": [76.47,18.33,76.62,18.48]},
  "asOf": "2024-03-26",
  "sunShareMm": 410.5,
  "scenes": [{"date": "2024-01-16", "id": "S2B_43QFA_20240116_0_L2A", "status": "ok|suspect"}],
  "ponds": [{
    "id": "P003", "lat": 18.3753, "lon": 76.535, "place": "near <village>",
    "maxAreaHa": 33.3, "areaNowHa": 18.9,
    "history": [{"date": "2024-01-16", "areaHa": 33.3, "valid": true}],
    "dryBy": {"earliest": "2024-04-28", "likely": "2024-05-12", "latest": "2024-06-01"},
    "daysLeft": {"min": 33, "likely": 47, "max": 67},
    "shrinkVsNeighbours": 2.7,
    "flag": "faster-than-sun" or null,
    "status": "dry|critical|watch|ok"
  }]
}
```

## API (AWS Lambda behind API Gateway HTTP API)
- GET /ponds?region=latur-2024&asOf=YYYY-MM-DD → ponds.json shape
- GET /ponds/{id}?region=...&asOf=... → one pond
- POST /plan {region, asOf, language: "en"|"mr"} → {markdown, pondIds}

## AI
- Plan writer: Strands Agents SDK (Python) on Amazon Bedrock (Claude model available in us-west-2). Tools: get_ponds(region, asOf), get_pond(id). Output: plan by period (for the 2024 replay: Jan–Mar, Apr–Jun) listing villages/ponds by urgency, ponds to inspect (flags), each line citing pond ids and our numbers. It must never invent numbers.
- Optional: for passes flagged "suspect", send a small true-colour crop to a Bedrock vision model, asking "water, dry bed, vegetation, or cloud/haze?" (JSON answer) to confirm or drop the reading.

## AWS ARCHITECTURE (region us-west-2, deployed with SAM)
- S3: pipeline outputs (ponds.json per region/asOf, image crops).
- Lambda "pipeline" (Python 3.12 container image with rasterio, pystac-client, numpy, scipy), triggered by EventBridge Scheduler every 5 days → writes S3 + DynamoDB. Fallback if Docker is a problem: run the pipeline locally, upload outputs to S3, and keep a scheduled Lambda that recomputes countdowns.
- DynamoDB: table Ponds (pk = regionId, sk = pondId) with history and latest countdown.
- Lambda "api" (Python) + API Gateway HTTP API.
- Bedrock (+ Strands) inside /plan.
- Amplify Hosting for the web app. CloudWatch logs (shown in the video).

## REPO LAYOUT
```
talaab/
  CLAUDE.md, README.md, LICENSE (MIT), .gitignore
  pipeline/  (Coder 1) talaab_pipeline/{stac.py, water.py, ponds.py, cleanup.py, evaporation.py, export.py}, run_replay.py, tests/, requirements.txt
  backend/   (Shlok) template.yaml, logic/{countdown.py, flags.py}, api/handler.py, agent/plan_agent.py, pipeline_lambda/Dockerfile, tests/
  web/       (Coder 2) Vite + React + Leaflet; public/mock/ponds.json
  data/latur-2024/  generated outputs committed for the demo
  docs/      demo script, architecture diagram, sources (Story teammate)
```

## TEAM
- Shlok (leader): Brain + AWS (backend/, logic, API, plan agent, SAM, integration)
- Nikhil (Coder 1): Satellite (pipeline/)
- Ranit (Coder 2): Web (web/)
- Bhavesh (Story, non-coder): docs/, slides, video, writeup, submission, testing

## TIMELINE
Thu = data + skeletons; Fri = countdown/flags + API + map with real data; Sat = AI plan + AWS schedule + deploy, FEATURE FREEZE 8 PM; Sun = fixes, video, writeup, submit by 5 PM IST.

=== END BRIEF ===
