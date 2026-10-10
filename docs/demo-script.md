# Demo video script (3:00, YouTube)

For Bhavesh. Every number below is checked against our data. **Don't change a number without asking
Shlok**, and don't promise anything the app doesn't do. Live numbers (the 2026 views) change every
5 days, so read them off the screen on recording day.

Site: https://main.duvnkrxj02sz1.amplifyapp.com · Record at 1920×1080, browser zoom 100%.

## Before recording (checklist)

- [ ] The schedule re-measures all of Marathwada at **06:00 IST on Sun 11 Oct** (then the 16th, 21st, ...). If you record
      before that, Shlok runs `python backend/scripts/run_district.py --marathwada --wait` (~17 min) shortly before, so the
      Step Functions graph and the CloudWatch dashboard show a fresh run.
- [ ] Tabs open in this order: (1) the site, (2) EventBridge Scheduler → Schedules → `talaab-live-marathwada`,
      (3) Step Functions → `talaab-marathwada` → latest execution → Graph view (then click one district's child run
      to show its Map of grid cells), (4) CloudWatch → Dashboards → `talaab-ops`, (5) the Talaab digest email in
      the inbox (subject "Talaab: … need action across Marathwada").
- [ ] AWS console region: **US West (Oregon)**. Hide account IDs and the email address (crop or blur).
- [ ] Close other tabs and notifications. Mouse moves slowly; pause half a second before each click.

## Shot list

| Time | Screen | Do | Say (narration) |
|---|---|---|---|
| 0:00–0:15 | Site landing page | Let it play, then click **Explore map** | "Maharashtra has declared drought in 265 of its 358 talukas. Villages live on small ponds, and in Latur's dry season the sun can take a metre of water off a pond while barely 4 cm of rain falls. Every district must file a water-scarcity plan by 15 October. Nobody tells them which pond runs dry, and when." |
| 0:15–0:40 | Map, "Whole district today" (Latur, live) | Hover the counts; open the **+ 7 more districts** list and pick **Nanded**; then go back to Latur | "Talaab watches every pond in all eight drought districts of Marathwada, 2,712 ponds, from free Sentinel-2 satellite passes on AWS, every five days. Each pond gets a dry-by **range**, not a fake date, and its taluka. Right after the monsoon many are still honestly 'too early to forecast'." |
| 0:40–1:15 | "Latur 2024" view | Click **Latur 2024**, press **Play** on the season timeline; stop around 5 Apr; click P003 | "To prove it works we replay 2024, a real drought year, using only what was known on each day. On 5 April Talaab marks P003 and P007 critical. P007 is dry on the 30 April pass, P003 by 5 May: 25 to 30 days of warning to send tankers." |
| 1:15–1:30 | P003 detail → **Satellite passes** strip | Scroll the strip; click one late thumbnail (it opens large) | "And you don't have to trust us: here is the satellite image behind every reading. Cloudy or suspect passes are marked and not used." |
| 1:30–1:45 | Alert timeline (left) | Point at the alert items | "Officers don't have to check the map. After every run Talaab sends one email for the whole division, listing each pond that turns critical, dries up, or starts shrinking much faster than its neighbours under the same sun, which suggests pumping. That's what the state's crackdown on illegal extraction needs." |
| 1:45–2:05 | **Accuracy** tab (Latur district 2024) | Scroll slowly | "We scored every forecast against what really happened. On a whole district, 435 ponds, 70% of our critical calls came true, with a median 25 days of warning. On a season we never trained on, 2023, two in three." |
| 2:05–2:20 | **Plan** tab (Whole district today) | Show the **By taluka** table; switch to **मराठी**, then back | "And Talaab drafts the quarterly scarcity plan the minister asked for, taluka by taluka and village by village, in English and Marathi, using only our numbers." |
| 2:20–2:50 | AWS console tabs 2 → 3 → 4 → 5 | Scheduler (2 s) → Step Functions graph, then one district's Map of cells (8 s) → dashboard (6 s) → email (3 s) | "It all runs serverless on AWS. Every five days EventBridge starts Step Functions; it splits each district into grid cells, each measured on its own Lambda, reading Sentinel-2 straight from AWS Open Data. All of Marathwada, 65,000 square kilometres, takes about seventeen minutes and costs nothing inside the free tier. Results land in S3 and DynamoDB, SNS sends the alerts, CloudWatch and X-Ray watch it, and the map itself is Amazon Location." |
| 2:50–3:00 | Back to the district map | Still | "All of Maharashtra would cost about a dollar thirty of compute a season. Talaab: the sun drinks first. Now we know when." |

## Facts you may say (and their source)

| Claim | Number | Source |
|---|---|---|
| Drought talukas | 265 of 358 (25 Sep 2026) | `CLAUDE.md` brief |
| Sun vs rain, Latur 2024 | ~974 mm evaporation (Jan to mid-June) vs ~43 mm rain (Jan–May) | `CLAUDE.md` brief (Open-Meteo) |
| 2024 replay alert | P003 and P007 critical on 5 Apr; dry 30 Apr / 5 May; 25–30 days warning | `docs/backtest-latur-2024.md` |
| Whole district (2024 replay) | 7,157 km², 435 ponds, 42 cells | `docs/scale-projection.md` |
| District accuracy | 70% of critical calls right, 60% caught in time, 25-day median warning | `docs/backtest-latur-district-2024.md` |
| Unseen season 2023 | 66% of critical calls right, 62% caught in time, 25 days | `docs/backtest-latur-2023.md` |
| Marathwada, live | 8 districts, 64,915 km², 403 cells, 2,712 ponds, 76 talukas; one run ~17 min, $0 in free tier ($0.15 without) | `docs/scale-projection.md` |
| Maharashtra | ~$1.30 of Lambda per full season (projection) | `docs/scale-projection.md` |

## Don't say

- That the AI plan is written by Bedrock today. It is built and tested, but AWS hasn't enabled Bedrock on
  our new account yet; the plan shown is the deterministic one (the tab says so).
- That the schedule ran by itself, **unless** you record after **Sun 11 Oct, 06:00 IST** (the first automatic run).
  Scheduler-started runs have random execution names; ours start with `marathwada-` or `<district>-`. Before then,
  say "runs every five days", which is true.
- A single dry date. Always "a range" or "likely around".
- That a flagged pond **is** being pumped. Say "suggests pumping; worth an inspection".

## Credits (end card or description)

Sentinel-2 L2A: contains modified Copernicus Sentinel data, via AWS Open Data and Element 84 Earth
Search. Weather: Open-Meteo (CC BY 4.0). Village names and taluka boundaries: © OpenStreetMap contributors (ODbL).
Basemap: Amazon Location Service (© AWS, HERE). Built by team Syntax Errors for WeMakeDevs × AWS Environmental Hacks.
