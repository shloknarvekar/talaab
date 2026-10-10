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
| A pumping flag that fired on half the district | Late April: 5 of 12 ponds flagged, ratios up to 13×, because the baseline included stable tanks | A flag that fires everywhere is useless to an inspector |
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
7. **A fair "faster than the sun" baseline.** Each pond is compared with the median shrink rate of ponds that are *actually shrinking* (at least 3). Before, big stable tanks pulled the median towards zero late in the season, so in late April 5 of 12 ponds were "faster than the sun", up to 13×. Now about 3 ponds are flagged, in mid-April only.

## Effect, measured one change at a time

Backtest on real Latur 2024 data as it stood on 8 Oct, 12 ponds (reproduce with `python backend/scripts/ablation.py`, which
reads that dataset from git). On 9 Oct the satellite pipeline was re-run with the imagery export; the same rules
now keep 13 ponds (the 36.7 ha tank near Kawa passes, because 20 mm of rain fell on 11–13 April 2024), and the
current 2024 scores are in `docs/backtest-latur-2024.md` (after the 9 Oct fix below: 50% flagged in time, 59% of calls right, 27.5-day warning).

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

## 9 Oct: judging suspect passes like for like (found at district scale)

**The problem.** Rule 1 compared a pass's *total* water area with its neighbours'. The total only
counts ponds that were clear on that pass. On the small box almost every pond is clear on every
usable pass, so that was fine. Across a whole district, a partly cloudy pass measures far fewer
ponds, so its total collapses although no water was lost. On the live district the 17 and 19 Sep
passes measured 214 and 124 ponds against 539 on 27 Sep: their totals fell about 62% and both
were thrown away. Compared over the ponds measured on *both* passes, the change was only −2% to −10%.
Losing them left most ponds with 3 passes over 10 days, under the 15 days a forecast needs, which
is why 276 of 383 live ponds were "too early".

**The fix.** A pass is now compared with each neighbouring pass over the ponds valid on both
(at least 3), and the median of those paired changes is tested against the same 40% threshold, with
the same rain and end-of-series rules. A pass that really is broken still fails: every pond it
measured reads low against the same ponds on its neighbours. Tests:
`pipeline/tests/test_cleanup.py` (`test_partly_cloudy_pass_is_not_suspect_when_compared_like_for_like`,
`test_paired_rule_still_catches_a_broken_pass`).

**Effect, same raw data, old rule → new rule:**

| | Suspect passes | Critical calls right | Caught in time | Median warning | Median error | Range hits |
|---|---|---|---|---|---|---|
| Live district 2026 | 2 → 0 | – | – | – | – | – ("too early" 276 → **164** of 383) |
| District 2024 (435 ponds) | 4 → 0 | 71% → 70% | 60% → 60% | 25 → 25 days | 19 → 19 days | 41% → 40% |
| Box 2024 (13 ponds) | 2 → 1 | 55% → **59%** | 50% → 50% | 27.5 → 27.5 days | 23 → **18.5** days | 48% → 45% |
| Box 2023, held out (19 → 18 ponds) | 5 → 2 | 70% → 66% | 62% → 62% | 25 → 25 days | 28 → **25** days | 32% → 33% |

Accuracy is about the same overall (one season up, one down by a few points, the district flat), and
the live district gets a forecast for about 100 more ponds. In 2023 the recovered passes also exposed
one more implausible signal (a "pond" that rose from 11.4 to 35.5 ha without rain), now excluded with
that reason. The change was made because of the live-district evidence, not to move a score, and the
before/after is published here.

**Cloud limit, tested rather than assumed.** We also tried admitting cloudier scenes. Scored on the
2024 district (same new rule), 45% and 60% tile cloud both made forecasts **worse** than 20%: critical
calls right 70% → 66%, median warning 25 → 20 days at 60%, and twice as many "predicted dry but
survived". Haze that the scene-classification mask misses seems to make ponds read low. So replays
keep the validated 20%. The live district keeps 45%, because right after the monsoon 20% leaves only
4 passes and 268 of 383 ponds "too early"; that costs about 4 points of precision (measured on 2024), and
we say so.

## 10 Oct: a confidence label on every countdown

A judge clicking the division's most urgent pond found Nanded P451 "dry 10-11 Oct" on three readings
(1.30, 1.12, then 0.08 ha a week later). A blunt rule (ignore ponds with a big single drop) would be wrong:
117 of the 259 ponds that really dried in the 2024 district replay also had one. So we label instead of
dropping: a countdown is **low confidence** when it rests on only 3 clear passes, or one pass carries more
than 60% of the drop in the window (`logic/countdown.py` `confidence`). Status is unchanged, so every
published backtest number stays the same. The label is worth having: low-confidence critical calls were
right far less often, in every season including the held-out one:

| Season | High-confidence critical calls right | Low-confidence critical calls right |
|---|---|---|
| Latur district 2024 (435 ponds) | 73% (621/847) | 57% (130/228) |
| Latur box 2024 | 84% (16/19) | 0% (0/8) |
| Latur box 2023 (held out) | 75% (40/53) | 33% (5/15) |

Lists (division urgent ponds, the AI briefing) now lead with high-confidence ponds; the plan marks the others
"low confidence: confirm on the next satellite pass". On 10 Oct, 27 of the 69 live critical ponds were low confidence.

## Honest limits

- We designed rules 1–4 after inspecting this same 2024 data. They're physically motivated and leave the synthetic results unchanged, but a fresh season or district is the real test.
- **Over-pessimism on big ponds:** 9 times we predicted a pond would dry before the end of May and it didn't. Large tanks shrink slower near the end than a straight line suggests. A shape-aware model (area vs depth) is the next step; we didn't tune for it here.
- Passes are 5 days apart and there was a 25-day gap in May (cloud), so "when did it dry" is itself only known to within a window.
- 12 real ponds is a small sample. The numbers show the direction, not a guarantee.
