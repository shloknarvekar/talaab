# Backtest: Latur (2023 held-out season)

> Every prediction below was made using only satellite passes and weather available on that date.

Replayed **28 satellite passes** (2023-01-21 to 2023-06-20) for **18 ponds**; **13** of them dried up during the season.

| Question | Talaab | Without heat adjustment |
|---|---|---|
| Actual dry date inside our predicted range | **33%** (60 of 184) | 35% |
| Median error of the likely date (+ = we said later) | 9 days | 11.5 days |
| "Critical" calls that came true within 30 days | **66%** (68 calls) | 69% |
| Ponds about to dry (≤ 30 days) that we had marked critical | **62%** | 60% |
| Median warning before a pond dried | **25 days** (11 ponds) | 20 days |
| Predicted dry, but the pond survived the season | 2 | 0 |

## Ponds that dried

| Pond | Actually dried between | First marked critical | Warning |
|---|---|---|---|
| P001 | 2023-05-31 and 2023-06-05 | never | - |
| P004 | 2023-04-11 and 2023-04-21 | 2023-04-06 | 15 days |
| P005 | 2023-05-26 and 2023-06-05 | 2023-05-11 | 25 days |
| P007 | 2023-06-05 and 2023-06-20 | 2023-05-21 | 30 days |
| P009 | 2023-06-05 and 2023-06-10 | 2023-05-31 | 10 days |
| P010 | 2023-03-07 and 2023-03-12 | 2023-02-15 | 25 days |
| P011 | 2023-05-26 and 2023-06-05 | 2023-05-21 | 15 days |
| P012 | 2023-03-22 and 2023-03-27 | never | - |
| P013 | 2023-03-12 and 2023-03-22 | 2023-01-31 | 50 days |
| P014 | 2023-03-07 and 2023-03-12 | 2023-01-31 | 40 days |
| P015 | 2023-05-21 and 2023-05-26 | 2023-03-27 | 60 days |
| P016 | 2023-02-25 and 2023-03-02 | 2023-02-20 | 10 days |
| P018 | 2023-04-11 and 2023-04-21 | 2023-04-06 | 15 days |

## How this is scored

- A pond counts as dry at the first clear pass below 5% of its largest area that stays below for the rest of the season. Passes are about 5 days apart, so the true dry date is a window, not a day.
- For each pass date we rebuild the forecast exactly as Talaab would have on that day, then compare.
- A range is a hit if it overlaps the actual dry window. Ponds that never dried are only judged when we predicted they would dry before the season ended.
- "Without heat adjustment" is the same model with the expected-evaporation scaling switched off.

Data: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search); Open-Meteo (CC BY 4.0).
