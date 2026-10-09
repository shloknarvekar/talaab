# Frontend redesign brief (Ranit leads · Shlok reviews)

**Deadline:** push branch `ranit-redesign` by **Saturday 2 PM IST** (freeze is 8 PM). Push every
few hours so Shlok can review early. Keep `npm run build` green.

## Who it is for

1. **Judges watching a 3-minute video** decide in the first 10 seconds whether this is real.
2. **A district officer** planning tankers: what is at risk, where, and by when.

Design is a judged criterion. The current site is functional but reads as a generic dashboard:
tiny text (8–11 px), a crammed top bar, dots instead of ponds, no story.

## Direction: bold storytelling

The site should feel like a front-page data story that is also a working tool.

- **Dark, map-first.** Full-bleed dark basemap (CARTO Dark Matter tiles, attribution
  "© OpenStreetMap contributors © CARTO") with Esri satellite as a toggle. Ponds glow in their
  status colour on the dark map.
- **One headline, huge.** The first thing anyone reads, generated from the data:
  > **1 pond in Latur will dry within a week. 1 is shrinking faster than the sun.**
  (Count `status === "critical"`, the soonest `daysLeft.likely`, and `flag === "faster-than-sun"`.)
- **Urgency colour ramp**, used consistently (map, pills, chart, alerts):

  | Status | Colour | Meaning shown to users |
  |---|---|---|
  | `dry` | `#7f1d1d` deep red | Dry now |
  | `critical` | `#ef4444` red | Dry within 30 days |
  | `watch` | `#f59e0b` amber | 30–90 days |
  | `ok` | `#14b8a6` teal | Lasts to the monsoon / stable |
  | `unknown` | `#64748b` slate | Too early to forecast |
  | flag | `#f97316` orange ring | Faster than the sun |

  Never rely on colour alone: always pair it with a label or icon.
- **Type:** UI in Inter (or system UI); headlines in a strong display face (e.g. "Space Grotesk"
  or "Fraunces"); Marathi in **"Noto Sans Devanagari"** or "Mukta" (Google Fonts). **Minimum
  13 px body, 12 px labels; key numbers 32–64 px.**
- **Motion with meaning only:** the season "plays", nothing bounces.

## Layout (desktop ≥ 1024 px)

```
┌────────────────────────────────────────────────────────────────────────────┐
│ जल Talaab   [Latur today ● LIVE] [Latur 2024 REPLAY]     Ponds  Plan  Accuracy  About │  thin top bar
├──────────────────────────┬─────────────────────────────────────────────────┤
│ HEADLINE (story)         │                                                 │
│ 1 pond will dry within   │            FULL-BLEED DARK MAP                  │
│ a week.                  │     glowing pond outlines / markers             │
│ ☀ 304 mm evaporated      │                                                 │
│ in 45 days               │                                   ┌───────────┐ │
│ ──────────────────────── │                                   │ POND      │ │
│ Most urgent first        │                                   │ DRAWER    │ │
│ ▸ P001 Khopegaon  7 d    │                                   │ (on click)│ │
│ ▸ P002 Chandeshwar 87 d  │                                   └───────────┘ │
├──────────────────────────┴─────────────────────────────────────────────────┤
│ ◀ ▶ PLAY   |──●──|──|──|──|──|── timeline of satellite passes ──|  15 Apr 2024 │  bottom timeline
└────────────────────────────────────────────────────────────────────────────┘
```

- **Timeline scrubber at the bottom** replaces the small slider: one tick per date in
  `region.dates`, labelled months, with a **▶ Play** button that steps through the season about
  every 0.8 s. **This is the demo moment:** ponds turn amber → red → dark as 2024 dries. In the
  replay, keep the banner "Each date shows only what Talaab knew that day".
- **Left panel:** the headline story, then the "sun's share" (`sunShareMm`), then the pond list,
  most urgent first, as large rows: id, village, status pill, days left, dry-by range.
- **Pond drawer (right, slides in):** big area number, a "shrunk %" ring, the dry-by range **with
  year**, the area chart (dark theme), the faster-than-sun callout, and the satellite thumbnail
  strip (see imagery).
- **Mobile (< 768 px):** map on top (55% height); the headline over it; a **bottom sheet** with
  the list that drags up; the pond drawer becomes a full-screen sheet; the timeline stays at the bottom.

## Pages

| Page | Content | API |
|---|---|---|
| **Map** (default) | Above | `GET /regions`, `GET /ponds?region=&asOf=` |
| **Plan** | Language toggle (English / मराठी); **load the plan automatically when the tab opens or the date/language changes** (no Generate click needed; keep a Regenerate button), rendered Markdown in a readable "document" card (light paper on dark, max 72 ch), **Print / Download PDF** (`window.print()` with a print stylesheet), source badge | `POST /plan` (poll while `status === "generating"`, already in `api.js`) |
| **Accuracy** | Three huge numbers (e.g. 50% flagged in time · 27.5 days warning · 55% calls right for 2024; always read from `GET /backtest`), the comparison table with **every** entry in `comparisons` as a column ("Before data cleanup", "Unseen 2023 season (held out)": the proof it generalises), ponds that dried | `GET /backtest?region=latur-2024` |
| **About** | The problem in 3 lines; how it works in 4 icons (satellite → measure → countdown + flag → plan & alert); AWS architecture (use `docs/architecture.md`); data credits; team; GitHub link | static |

Coming from Shlok (backend), Saturday morning:
- `GET /alerts?region=` gives a timeline of alerts ("On 26 Mar Talaab would have emailed: P006 turned critical"). Show it as a vertical feed on the Map page in the replay, synced to the timeline.

## Imagery (with Nikhil)

Follow `docs/imagery-contract.md`: draw `outlines.geojson` as glowing polygons in status colour
(markers become small labels on top). Add a thumbnail strip in the drawer, showing **only passes
≤ current as-of date**. If `index.json` is missing, hide both silently.

## Non-negotiables (judges and officials check these)

1. **No forecasting maths in the browser.** Every status, range and flag comes from the API (`api.js` stays the only data layer).
2. **Ranges, never a single date**, and always with the year.
3. **Replay vs live is always visible.**
4. **Credits visible:** Sentinel-2 (Copernicus) via AWS Open Data · Open-Meteo (CC BY 4.0) · © OpenStreetMap contributors (+ CARTO if used).
5. **Accessible:** text contrast ≥ 4.5:1 on dark, keyboard-usable list, timeline and tabs, visible focus rings, `prefers-reduced-motion` disables Play animation.
6. **Show uncertainty honestly:** "Too early to forecast", excluded detections ("5 detections excluded, why?"), and "suggests pumping, not proof".
7. **Fast:** no heavy new libraries (no UI kits, no map libraries other than Leaflet). Lazy-load Recharts if possible.

## Done means

- Desktop 1440×900 and phone 390×844 both look intentional (send screenshots of both).
- The Play button runs the whole 2024 season smoothly.
- `npm run build` passes; there are no console errors; `python backend/scripts/smoke_test.py` still passes.
- Shlok merges, then runs `python backend/scripts/deploy_web.py`.
