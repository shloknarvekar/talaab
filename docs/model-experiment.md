# Experiment: does a shape-aware countdown predict big tanks better?

Written **before** running it (9 Oct 2026, 04:20 IST), so the decision rule can't be bent to fit
the results.

## Why

On the real 2024 backtest, Talaab predicted 9 times that a pond would dry before the end of May,
and it didn't. These are mostly big tanks. The countdown assumes area shrinks in a straight line.

Physics: a pond's **water level** falls at a fairly steady rate (evaporation plus use). How fast its
**area** falls depends on shape:

| Shape | Area vs depth | Area over time (steady level drop) |
|---|---|---|
| Saucer (paraboloid) | A ∝ h | straight line, which is the current model |
| Cone / V-shaped tank | A ∝ h² | √A falls in a straight line: fast at first, **slower near the end** |

So a cone-shaped tank dries later than a straight line through its recent areas suggests.

## Candidates

- **L (current):** robust (Theil–Sen) straight line through area.
- **S (cone):** robust straight line through **√area**; dry when √A reaches √(5% of max).
- **A (auto, per pond):** fit both on the pond's own last 45 days and use whichever fits better
  (lower median absolute error in hectares). A tie goes to L.

The heat adjustment and the ±SE / ±20% range rules stay identical for every candidate.
"Faster than the sun" still uses the straight-line area slope, so flags are unaffected.
No candidate has a parameter fitted across ponds, so nothing is tuned on the test data.

## Data

- **Development:** Latur 2024 (real, 12 ponds) and synthetic.
- **Held-out final exam:** **Latur Jan–Jun 2023**, produced by the same pipeline and quality rules,
  and never used to design any rule or model. (Caveat: the "expected heat" climatology is
  2019–2023, which includes 2023 itself; it is a 30-day average, so the leak is small and noted.)

## Decision rule (fixed in advance)

A candidate is adopted only if, **on 2023 held-out**, against L:
1. Critical recall and critical precision each drop by no more than 3 points, **and**
2. Median absolute error of the likely date **or** "predicted dry but survived" improves, **and**
3. The range hit rate drops by no more than 5 points.

If both S and A qualify, take the one with the lower 2023 median absolute error. If neither
qualifies, **keep L** and publish the result anyway. 2024 and synthetic numbers are reported
next to it for context, but they don't decide.

## Result

_To be filled in after running `python backend/scripts/shape_experiment.py`._
