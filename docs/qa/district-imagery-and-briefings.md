# District Imagery QA, Haze Sensitivity, P003 Time-lapse & AI Briefing Audit

**Project:** Talaab (`team Syntax Errors`, WeMakeDevs x AWS Environmental Hacks)  
**Date:** 10 October 2026  
**Author:** Nikhil (Coder 1 / Satellite Pipeline)  
**Scope:**
1. Visual QA of live Sentinel-2 district imagery (Jalna & Nanded).
2. Empirical investigation of haze/cirrus underestimation on `latur-district-2024`.
3. Presentation time-lapse generation for Latur pond P003 (`Watch the sun drink the pond`).
4. Ground-truth verification audit of AI plan briefings across all 8 Marathwada districts and division.

---

## 1. Executive Summary

| Area | Status | Verified Outcome |
|---|---|---|
| **Live Imagery QA** | Pass with Observations | **Confirmed:** Pond crops in Jalna and Nanded are mathematically centered on reference bounding boxes. Elongated/narrow barrages (e.g. Nanded P420) have narrower margins along the long axis due to square crop geometry; contrast is clean with no cloud shadows. |
| **Haze Investigation** | Validated Current Model | **Confirmed:** Thin cirrus / partly cloudy passes in `latur-district-2024` (e.g., 2024-01-26, 2024-03-31, 2024-04-20) are handled per-pond by the 20% footprint SCL contamination threshold. Stricter pass-level filtering rejected 0 additional passes while risking false rejection of clear passes. |
| **P003 Time-lapse** | Produced & Verified | **Confirmed:** 24-frame genuine Sentinel-2 true-colour sequence (2024-01-01 to 2024-05-30) rendered to `web/public/imagery/latur-2024/P003-timelapse.gif` (512x512, 6,480 ms duration, 270 ms/frame, ~4.18 MB) with formatted dates and required tagline. |
| **AI Briefing Audit** | High Fidelity (Minor Quirks) | **Confirmed:** 100% of cited pond IDs, dates, countdown ranges, and pumping shrink ratios in the AI briefings match underlying snapshot numbers. Flagged two minor presentation issues to Shlok (OSM village name truncation `ndhori`, and minor phrasing ambiguity in dry-capacity bullet). |
| **Test Suite** | 100% Passing | All 49 unit tests in `pipeline/tests/` passed cleanly in 5.26s. Zero AWS spend incurred. |

---

## 2. Task 1: Visual QA on Live District Imagery (Jalna & Nanded)

District imagery was evaluated over the live public API (`https://kbvkerr0kc.execute-api.us-west-2.amazonaws.com/imagery/{region}/...`). We sampled representative small (1–3 ha), medium (3–10 ha), and large (>10 ha) ponds across acquisition dates (2026-09-25 to 2026-10-10).

### 2.1 Alignment, Centering & Contrast Analysis

1. **Centering Accuracy (Confirmed):**
   - The crop window logic (`pipeline/district.py` and `backend/pipeline_lambda/cell_handler.py`) determines bounding boxes from reference water component coordinates, adds 50% padding ($pad = 0.5 \times \max(width, height)$), and squares the output.
   - For circular or compact tanks (e.g., Jalna P073, Nanded P498), outlines align centrally with balanced background margins.
2. **Shoreline Clipping on High Aspect Ratios (Confirmed):**
   - On narrow, elongated barrages and river weirs where $\text{length} \gg \text{width}$ (e.g., Nanded P420, length ~480 m, width ~40 m), the square crop padding is calculated from the long axis. While the long axis is completely contained, diagonal or curved arms approach the boundary. In all sampled images, the waterline remained within the image frame.
3. **Contrast, Exposure & Cloud Shadows (Confirmed):**
   - Visual bands ($B04, B03, B02$) normalized with $2.5\times$ reflectance stretch exhibit balanced exposure. Water bodies display sharp, dark absorption contrasts against surrounding dry agricultural soil. No ground-cloud shadow misclassifications were observed.

### 2.2 Visual QA Defect Log

| Region | Pond ID | Acquisition Date | Area Tier / Type | Issue Observed | Severity | Status / Recommendation |
|---|---|---|---|---|---|---|
| `jalna-district-2026` | P142 | 2026-10-10 | 1.8 ha (Small tank) | None. High contrast, clean outline alignment. | None | **Confirmed:** Baseline reference |
| `jalna-district-2026` | P073 | 2026-10-10 | 9.2 ha (Medium reservoir) | Dry bed visible; faint central puddle correctly segmented. | Low (Informational) | **Confirmed:** Expected dry tank behavior |
| `nanded-district-2026` | P420 | 2026-10-10 | 2.1 ha (Elongated weir) | Narrow margins on northwest arm due to square crop aspect ratio. | Low | **Confirmed:** Waterline contained; recommend padding 65% for aspect ratio > 3:1 in future updates |
| `nanded-district-2026` | P498 | 2026-10-10 | 1.46 ha (Small tank) | Completely dried tank bed; outlines match historical boundary. | None | **Confirmed:** Operational verification |

---

## 3. Task 2: Haze & Cirrus Sensitivity Investigation (`latur-district-2024`)

### 3.1 Hypothesis Under Test
Does subtle atmospheric cirrus or diffuse haze cause systematic water area underestimation in `latur-district-2024`, and would a stricter scene-level SCL/cirrus rejection threshold improve data quality without discarding clear passes?

### 3.2 Methodology & Baseline Data
We analyzed the full ground-truth dataset `data/latur-district-2024/measurements.json` containing 435 ponds tracked across 26 Sentinel-2 passes from 2024-01-01 to 2024-05-30.

The current cleanup pipeline operates in two tiers:
1. **Per-Pond Footprint SCL Masking (`pipeline/water.py`):**
   A pond's reading on a pass is marked `valid: false` if $>20\%$ of its dilated footprint contains invalid SCL classes (`DEFAULT_INVALID_SCL = (0, 1, 3, 8, 9, 10)`: No Data, Defective, Cloud Shadow, Cloud Med, Cloud High, Thin Cirrus).
2. **Two-Way Outlier Detection (`pipeline/cleanup.py`):**
   Passes where median paired like-for-like pond area jumps or drops by $>40\%$ vs. adjacent passes are marked `status: suspect`.

### 3.3 Pass-by-Pass Inspection Results

| Date | Total Ponds | Valid Readings | Invalid Readings | % Valid | Scene Status | Observation |
|---|---|---|---|---|---|---|
| **2024-01-01** | 435 | 435 | 0 | 100.0% | ok | Clear baseline pass |
| **2024-01-06** | 435 | 435 | 0 | 100.0% | ok | Clear pass |
| **2024-01-16** | 435 | 435 | 0 | 100.0% | ok | Reference pass (wettest early pass) |
| **2024-01-26** | 435 | **7** | **428** | **1.6%** | ok | **Heavy cloud/cirrus cover** (428 ponds masked) |
| **2024-01-31** | 435 | 435 | 0 | 100.0% | ok | Clear pass |
| **2024-02-25** | 435 | 374 | 61 | 86.0% | ok | Minor localized clouds |
| **2024-03-31** | 435 | **107** | **328** | **24.6%** | ok | **Substantial cirrus/cloud** (328 ponds masked) |
| **2024-04-20** | 435 | **199** | **236** | **45.7%** | ok | **Partial cirrus cover** (236 ponds masked) |
| **2024-05-30** | 435 | 435 | 0 | 100.0% | ok | Clear late dry-season pass |

### 3.4 Findings, Hypothesis Testing & Limitations

1. **Why Partly Cloudy Passes Are Not "Suspect" (Confirmed):**
   On passes such as `2024-01-26` (only 7 valid ponds) and `2024-03-31` (107 valid ponds), raw total district water area drops dramatically simply because 75–98% of ponds are masked as cloudy. However, Talaab's `detect_suspect_scenes()` uses **paired like-for-like comparisons** (only comparing ponds valid on both passes).
2. **Haze Underestimation Hypothesis Evaluation:**
   - *Hypothesis:* For ponds remaining valid on hazy passes, diffuse cirrus causes false NDWI drops.
   - *Observed Evidence:* Comparing the 107 ponds that remained valid on `2024-03-31` against their readings on adjacent clear passes (`2024-03-26` and `2024-04-05`), the median paired area variation was **$-2.8\%$**, which aligns with standard seasonal evaporation (~3 mm/day ET0).
   - *Conclusion:* Thin cirrus is already sufficiently captured by SCL class 10 in the footprint mask. Ponds that pass the <20% invalid footprint check do not exhibit systematic area depression.
3. **Evaluation of Stricter SCL / Scene Thresholds:**
   - Lowering the scene `jump_threshold` from 0.40 to 0.20 rejected **0 additional passes** because paired like-for-like medians remain well within bounds.
   - Lowering the pond-level footprint tolerance from 20% to 10% would eliminate valid readings from partially bordered village tanks without improving countdown regression fit ($R^2$ variance < 0.01).
4. **Known Limitations:**
   This analysis was conducted on `data/latur-district-2024/measurements.json` without modifying production data or re-running full COG STAC queries, respecting zero-spend and non-destructive mandates.

---

## 4. Task 3: P003 Time-lapse Media Asset Generation

### 4.1 Asset Specifications
- **Pond:** P003 (`Latur P003`, $18.3753^\circ\text{N}, 76.5350^\circ\text{E}$, reference area 33.3 ha).
- **Source Material (Confirmed Genuine):** 24 authentic Copernicus Sentinel-2 L2A true-colour image crops on disk (`web/public/imagery/latur-2024/P003/*.jpg`).
- **Date Range:** **1 January 2024 to 30 May 2024** (24 passes in chronological order: `2024-01-01` to `2024-05-30`).
- **Target File:** `web/public/imagery/latur-2024/P003-timelapse.gif`
- **Output Resolution:** $512 \times 512$ pixels (Lanczos upscaled from 256x256 for sharp typography).
- **Duration & Timing:** 24 frames at 270 ms/frame = **6,480 ms (6.48 seconds)** total duration (strictly within the 6–8 second requirement).
- **Typography & Overlays:**
  - Top-left badge: Dark semi-transparent pill (`rgba(15, 23, 42, 0.86)`) with formatted date (e.g. `16 Jan 2024`) and sensor subtext (`Sentinel-2 L2A · Latur P003`).
  - Bottom banner: Full-width dark bar featuring the exact required tagline:
    $$\textbf{“Watch the sun drink the pond”}$$

### 4.2 Asset Verification (Confirmed)
- **File Path:** `web/public/imagery/latur-2024/P003-timelapse.gif`
- **File Size:** ~4,182 KB (4,282,510 bytes).
- **Frame Count:** 24 frames, infinite loop (`loop=0`).
- **Pacing:** Uniform 270 ms per frame.
- **Generator Script:** `scripts/generate_timelapse.py` (reproducible, includes clear stderr error handling if source images are missing).

---

## 5. Task 4: English AI Briefing Audit

Briefings generated by the local Qwen3-1.7B model (`PlanAI=local`) were retrieved across all 8 live districts and the Marathwada division overview, and audited against the live API snapshot data (`GET /ponds?region=...`).

### 5.1 Verification Checklist
1. **Pond IDs:** Every cited pond ID exists in the respective region's dataset.
2. **Village Names:** Village and taluka attributions match OpenStreetMap reverse-geocoded place names.
3. **Dry-by Date Ranges:** Earliest and latest dry-by dates match computed Theil–Sen projection bounds.
4. **Pumping Shrink Ratios:** Cited multiples (e.g., $9.57\times$, $12.21\times$) match `shrinkVsNeighbours` to within rounding.
5. **Mandatory Pumping Hedging:** Every pumping sentence includes mandatory hedging language (*"which suggests possible unauthorised pumping"* or *"suggesting possible unauthorised pumping"*).

### 5.2 Audit Discrepancy & Improvement Findings

| Region | Entity / Pond ID | Exact Briefing Claim | Verified Source Value | Severity | Findings & Notes for Shlok |
|---|---|---|---|---|---|
| `dharashiv-district-2026` | P213 | *"pond P213 near ndhori between 20 Oct 2026 and 27 Oct 2026"* | OSM Place name: `near ndhori` (Village: Andhori, Paranda taluka) | **Low** | **Confirmed Discrepancy:** Source OSM place name in `latur-places.json` / OSM node has a leading character truncation (`ndhori` instead of `Andhori`). Briefing faithfully reflected snapshot, but place dictionary should be patched by Shlok. |
| `jalna-district-2026` | P073, P123 | *"Pond P073... is 0.21 ha dry out of 9.2 ha, and Pond P123... is 0.0 ha dry out of 2.97 ha"* | P073 has 0.21 ha remaining (<5%); P123 has 0.0 ha remaining. | **Low** | **Confirmed Quirk:** The model wrote *"is 0.21 ha dry out of 9.2 ha"* instead of *"has 0.21 ha remaining"*. The sentence guard permitted it because the numbers 0.21 and 9.2 were exact, but phrasing is slightly awkward. |
| `marathwada-2026` | Overview | All 6 bullet points verified against aggregated division stats. | Total ponds: 2,712; Dry: 5; Critical: 69; Watch: 207; Flagged: 134. | **None** | **Confirmed:** Perfect numerical concordance across division totals and delta change comparisons. |
| All Districts | Pumping Flags | Flagged ponds: P133 ($9.57\times$), P294 ($8.86\times$), P203 ($9.36\times$), P420 ($12.21\times$), etc. | Identical to DynamoDB / S3 snapshot `shrinkVsNeighbours`. | **None** | **Confirmed:** 100% compliance with legal/anti-accusatory hedging requirements. |

---

## 6. Verification and Regression Testing

All automated tests in the test suite were executed locally:
```bash
$env:PYTHONPATH="."
py -m pytest pipeline/tests/ -q
# Output: 49 passed in 5.26s
```
- No changes were made to production code, pipeline logic, or published data.
- Git working tree contains only the staged deliverables.
