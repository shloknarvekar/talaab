# Backtest: Latur (2024 replay, SYNTHETIC data)

> **Synthetic data.** These numbers test the scoring code, not the method: the synthetic ponds were built to shrink with the heat, so the heat adjustment wins by construction. Re-run on real data.

Replayed **27 satellite passes** (2024-02-05 to 2024-06-14) for **14 ponds**; **7** of them dried up during the season.

| Question | Talaab | Without heat adjustment |
|---|---|---|
| Actual dry date inside our predicted range | **79%** (104 of 131) | 47% |
| Median error of the likely date (+ = we said later) | 7 days | 20 days |
| "Critical" calls that came true within 30 days | **78%** (51 calls) | 73% |
| Ponds about to dry (≤ 30 days) that we had marked critical | **93%** | 81% |
| Median warning before a pond dried | **30 days** (7 ponds) | 25 days |
| Predicted dry, but the pond survived the season | 0 | 0 |

## Ponds that dried

| Pond | Actually dried between | First marked critical | Warning |
|---|---|---|---|
| P003 | 2024-04-20 and 2024-04-25 | 2024-03-26 | 30 days |
| P007 | 2024-04-25 and 2024-04-30 | 2024-04-15 | 15 days |
| P008 | 2024-06-04 and 2024-06-09 | 2024-05-10 | 30 days |
| P009 | 2024-05-25 and 2024-05-30 | 2024-04-30 | 30 days |
| P011 | 2024-05-10 and 2024-05-15 | 2024-04-15 | 30 days |
| P012 | 2024-05-15 and 2024-05-20 | 2024-04-20 | 30 days |
| P013 | 2024-03-06 and 2024-03-21 | 2024-02-15 | 35 days |

## How this is scored

- A pond counts as dry at the first clear pass below 5% of its largest area that stays below for the rest of the season. Passes are about 5 days apart, so the true dry date is a window, not a day.
- For each pass date we rebuild the forecast exactly as Talaab would have on that day, then compare.
- A range is a hit if it overlaps the actual dry window. Ponds that never dried are only judged when we predicted they would dry before the season ended.
- "Without heat adjustment" is the same model with the expected-evaporation scaling switched off.

Data: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search); Open-Meteo (CC BY 4.0).
