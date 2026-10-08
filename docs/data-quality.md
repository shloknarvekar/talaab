# What the real data taught us (and what we changed)

Our first backtest on real Sentinel-2 data from Latur 2024 was much weaker than on synthetic
data: only **32%** of ponds about to dry had been marked critical. Instead of tuning numbers until
they looked good, we looked at every pond's raw readings, pass by pass. The problem was mostly in
the data, not the countdown maths.

## What we found

| Problem | Example (Latur 2024) | Why it matters |
|---|---|---|
| A broken pass hit every pond at once and was not caught | 6 Jan: P002 read 34.9 → **1.1** → 31.2 ha; P005 19.2 → **0.0** → 18.0 | The cleanup only caught sudden *rises*; drops passed as real |
| The wrong pass got blamed | 11 Jan was marked suspect only because 6 Jan before it was so low | Good data was thrown away while bad data stayed |
| Readings on suspect passes were still used | Any pond on a suspect pass | "Suspect" had no effect on the maths |
| "Ponds" that were never really there | Four detections with water on the reference date only (one of them on a cloudy reference reading) | They "dried" in week one and counted as missed predictions |
| A signal that is not water level | One 37 ha detection climbed 6.9 → 41.5 ha in March–April with no rain | Water cannot do that in a drought; vegetation, turbidity or shadow can |
| Single-pass dips kept | 7.8 → **0.9** → 6.9 ha | One bad reading tilts a straight-line fit |
| Countdowns from too little data (live) | 3 passes over 10 days after the monsoon: 73.7 → 42.1 → 23.6 ha | Receding floodwater looks like a pond drying in 4 days |

## What we changed

All rules are physical, written down and tested
([`pipeline/cleanup.py`](../pipeline/cleanup.py), [`backend/logic/countdown.py`](../backend/logic/countdown.py)):

1. **Suspect passes work both ways.** A pass is suspect if the district's total water is more than 40% away from its neighbouring passes. Upward jumps count only when rain can't explain them; drops count only when water comes back afterwards. The worst outlier is removed first, so it can't make its neighbours look wrong. Readings on suspect passes are no longer used.
2. **Dips as well as spikes.** A reading that halves and then recovers is dropped (both changes ≥ 0.3 ha, to ignore tiny-pond noise).
3. **A pond must exist.** It needs water near its reference size on at least half the clear passes within 15 days of the reference date, judged *before* spike cleaning so the evidence isn't removed. Otherwise it is excluded and the reason is recorded in `excludedPonds`.
4. **A pond can't refill in a drought.** A rise of more than half its size without 10 mm of rain means the signal isn't measuring water. It is excluded, with the reason. This is only judged when rain data exists.
5. **Robust trend.** The countdown uses a Theil–Sen fit (median of pairwise slopes) instead of ordinary least squares, so one bad reading can't tilt it.
6. **Enough data before a countdown.** At least 3 clear passes spanning 15 days; until then the status is `unknown`.

## Effect, measured one change at a time

Backtest on real Latur 2024 data (reproduce with `python backend/scripts/ablation.py`):

| | Before | Clean data | Robust fit | **Both** |
|---|---|---|---|---|
| Ponds about to dry (≤ 30 days) that we had marked critical | 32% | 57% | 44% | **61%** |
| "Critical" calls that came true within 30 days | 54% | 57% | 58% | **61%** |
| Median warning before a pond dried | 22.5 days | 27.5 days | 25 days | **27.5 days** |
| Median error of the likely dry date | 24 days | 21 days | 24 days | **18 days** |
| Actual dry date inside our predicted range | 38% | 45% | 42% | **45%** |
| Predicted dry, but the pond survived the season | 5 | 7 | 6 | **9** |

- On synthetic data the same changes move nothing (79% → 80% range hits), so they fix real-data problems rather than gaming the score.
- With clean data, the **heat adjustment now helps**: 45% of dry dates fall inside the range with it, 37% without it.
- Rule 6 changes no 2024 number; it only stops early-season false alarms on the live map.

## Honest limits

- We designed rules 1–4 after inspecting this same 2024 data. They're physically motivated and leave the synthetic results unchanged, but a fresh season or district is the real test.
- **Over-pessimism on big ponds:** 9 times we predicted a pond would dry before the end of May and it didn't. Large tanks shrink slower near the end than a straight line suggests. A shape-aware model (area vs depth) is the next step; we didn't tune for it here.
- Passes are 5 days apart and there was a 25-day gap in May (cloud), so "when did it dry" is itself only known to within a window.
- 12 real ponds is a small sample. The numbers show the direction, not a guarantee.
