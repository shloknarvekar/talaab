# Demo video script (3:00, YouTube)

For Bhavesh. Every number below is checked against our data. **Don't change a number without asking
Shlok**, and don't promise anything the app doesn't do. Live numbers (the 2026 views) change every
5 days, so read them off the screen on recording day.

Site: https://main.duvnkrxj02sz1.amplifyapp.com · Record at 1920×1080, browser zoom 100%.

## Before recording (checklist)

- [ ] If recording before Sun 11 Oct 06:00 IST: Shlok runs `python backend/scripts/run_district.py --region latur-district-2026 --wait`
      ~10 min before recording, so the Step Functions graph and the CloudWatch dashboard show a fresh run.
      After that time, use the automatic 11 Oct run instead.
- [ ] Tabs open in this order: (1) the site, (2) EventBridge Scheduler → Schedules → `talaab-live-district`,
      (3) Step Functions → `talaab-district` → latest execution → Graph view, (4) CloudWatch → Dashboards →
      `talaab-ops`, (5) the Talaab alert email in the inbox (subject "Talaab: … need action in Latur district").
- [ ] AWS console region: **US West (Oregon)**. Hide account IDs and the email address (crop or blur).
- [ ] Close other tabs and notifications. Mouse moves slowly; pause half a second before each click.

## Shot list

| Time | Screen | Do | Say (narration) |
|---|---|---|---|
| 0:00–0:20 | Site, "Whole district today" view (it opens there) | Nothing; let the map settle | "Maharashtra has declared drought in 265 of its 358 talukas. Villages live on small ponds, and in Latur's dry season the sun can take a metre of water off a pond while barely 4 cm of rain falls. Every district must file a water-scarcity plan by 15 October. Nobody tells them which pond runs dry, and when." |
| 0:20–0:45 | Same | Hover the counts; click the most urgent pond in the list | "Talaab watches every pond in Latur district, 383 this season, from free Sentinel-2 satellite passes on AWS, every five days. Each pond gets a dry-by **range**, not a fake date, and a status. Right after the monsoon most are honestly 'too early to forecast'." |
| 0:45–1:20 | "Latur 2024" view | Click **Latur 2024**, press **Play** on the season timeline; stop around 5 Apr; click P003 | "To prove it works we replay 2024, a real drought year, using only what was known on each day. On 5 April Talaab marks P003 and P007 critical. P007 is dry on the 30 April pass, P003 by 5 May: 25 to 30 days of warning to send tankers." |
| 1:20–1:35 | P003 detail → **Satellite passes** strip | Scroll the strip; click one late thumbnail (it opens large) | "And you don't have to trust us: here is the satellite image behind every reading. Cloudy or suspect passes are marked and not used." |
| 1:35–1:50 | Alert timeline (left) | Point at the alert items | "Officers don't have to check the map. Talaab emails them the moment a pond turns critical, dries up, or starts shrinking much faster than its neighbours under the same sun, which suggests pumping. That's what the state's crackdown on illegal extraction needs." |
| 1:50–2:10 | **Accuracy** tab | Scroll slowly | "We scored every forecast against what really happened. On the whole district, 435 ponds, 71% of our critical calls came true, with a median 25 days of warning. On a season we never trained on, 2023, 70%." |
| 2:10–2:25 | **Plan** tab | Switch to **मराठी**, then back; hover "Download / print" | "And Talaab drafts the quarterly scarcity plan the minister asked for, in English and Marathi, village by village, using only our numbers." |
| 2:25–2:50 | AWS console tabs 2 → 3 → 4 → 5 | Scheduler (2 s) → Step Functions graph (show the Map with 42 cells, 6 s) → dashboard (5 s) → email (3 s) | "It all runs serverless on AWS. EventBridge starts Step Functions every five days; it splits the district into 42 cells, each measured on its own Lambda, reading Sentinel-2 straight from AWS Open Data. The whole district takes under three minutes and costs nothing inside the free tier. Results land in S3 and DynamoDB, and SNS sends the alerts." |
| 2:50–3:00 | Site, About page or back to the district map | Still | "Every district in Maharashtra would cost about a dollar thirty a season. Talaab: the sun drinks first. Now we know when." |

## Facts you may say (and their source)

| Claim | Number | Source |
|---|---|---|
| Drought talukas | 265 of 358 (25 Sep 2026) | `CLAUDE.md` brief |
| Sun vs rain, Latur 2024 | ~974 mm evaporation (Jan to mid-June) vs ~43 mm rain (Jan–May) | `CLAUDE.md` brief (Open-Meteo) |
| 2024 replay alert | P003 and P007 critical on 5 Apr; dry 30 Apr / 5 May; 25–30 days warning | `docs/backtest-latur-2024.md` |
| Whole district | 7,157 km², 435 ponds (2024), 42 cells, 161 s, $0 | `docs/scale-projection.md` |
| District accuracy | 71% of critical calls right, 60% caught in time, 25-day median warning | `docs/backtest-latur-district-2024.md` |
| Unseen season 2023 | 70% of critical calls right, 62% caught in time, 25 days | `docs/backtest-latur-2023.md` |
| Live district | 383 ponds on 9 Oct 2026; first live run 60 s | `data/latur-district-2026/run.json` |
| Maharashtra | ~$1.30 of Lambda per full season (projection) | `docs/scale-projection.md` |

## Don't say

- That the AI plan is written by Bedrock today. It is built and tested, but AWS hasn't enabled Bedrock on
  our new account yet; the plan shown is the deterministic one (the tab says so).
- That the schedule ran by itself, **unless** you record after **Sun 11 Oct, 06:00 IST**. The schedules fire on
  the 1st, 6th, 11th, 16th, 21st, 26th and 31st of each month (06:00 IST district, 06:30 IST recompute), so the
  first automatic run is 11 Oct. After that, the Step Functions execution list shows it (scheduler-started
  runs are not named `latur-district-...`; ours are). Before then, say "runs every five days", which is true.
- A single dry date. Always "a range" or "likely around".
- That a flagged pond **is** being pumped. Say "suggests pumping; worth an inspection".

## Credits (end card or description)

Sentinel-2 L2A: contains modified Copernicus Sentinel data, via AWS Open Data and Element 84 Earth
Search. Weather: Open-Meteo (CC BY 4.0). Village names and basemap: © OpenStreetMap contributors (ODbL).
Built by team Syntax Errors for WeMakeDevs × AWS Environmental Hacks.
