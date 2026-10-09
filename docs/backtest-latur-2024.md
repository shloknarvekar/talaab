# Backtest: Latur (2024 replay)

> Every prediction below was made using only satellite passes and weather available on that date.

Replayed **20 satellite passes** (2024-01-21 to 2024-05-30) for **13 ponds**; **7** of them dried up during the season.

| Question | Talaab | Without heat adjustment |
|---|---|---|
| Actual dry date inside our predicted range | **45%** (44 of 97) | 38% |
| Median error of the likely date (+ = we said later) | 10 days | 17.5 days |
| "Critical" calls that came true within 30 days | **59%** (27 calls) | 58% |
| Ponds about to dry (≤ 30 days) that we had marked critical | **50%** | 47% |
| Median warning before a pond dried | **27.5 days** (4 ponds) | 25 days |
| Predicted dry, but the pond survived the season | 9 | 7 |

## Ponds that dried

| Pond | Actually dried between | First marked critical | Warning |
|---|---|---|---|
| P001 | 2024-05-05 and 2024-05-30 | never | - |
| P003 | 2024-04-30 and 2024-05-05 | 2024-04-05 | 30 days |
| P006 | 2024-05-05 and 2024-05-30 | 2024-05-05 | 25 days |
| P007 | 2024-04-25 and 2024-04-30 | 2024-04-05 | 25 days |
| P008 | 2024-05-05 and 2024-05-30 | never | - |
| P010 | 2024-02-10 and 2024-02-20 | 2024-01-21 | 30 days |
| P012 | 2024-04-30 and 2024-05-05 | never | - |

## How this is scored

- A pond counts as dry at the first clear pass below 5% of its largest area that stays below for the rest of the season. Passes are about 5 days apart, so the true dry date is a window, not a day.
- For each pass date we rebuild the forecast exactly as Talaab would have on that day, then compare.
- A range is a hit if it overlaps the actual dry window. Ponds that never dried are only judged when we predicted they would dry before the season ended.
- "Without heat adjustment" is the same model with the expected-evaporation scaling switched off.

Data: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search); Open-Meteo (CC BY 4.0).
