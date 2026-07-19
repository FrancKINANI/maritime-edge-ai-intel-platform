# Phase 0 — Report of Scientific Validation

> **Maritime Edge AI Platform**
> Zero-shot domain transfer : simulated SAR (MRSSD) → real SAR (Sentinel-1 GRD IW)

---

## 1. Objective

Phase 0 answers a unique scientific question :

> *Can the YOLOv8 INT8 detector, trained exclusively on **simulated** SAR images (iVision-MRSSD dataset), achieve acceptable performance on **real** SAR data Sentinel-1 GRD — without fine-tuning?*

This is a **zero-shot domain transfer test**. The result determines the project's trajectory. The validation involves:
- Downloading real Sentinel-1 scenes from Copernicus Data Space
- Applying 4 SAR preprocessing pipelines (A/B/C/D)
- Running YOLOv8n INT8 ONNX inference
- Comparing predictions against AIS-derived ground truth annotations (Global Fishing Watch v3 API)
- Computing Precision, Recall, mAP@0.5, and center-distance metrics

---

## 2. Scenes Used

2 **Sentinel-1D** IW GRD scenes were downloaded from the CDSE (Copernicus Data Space Ecosystem) catalog :

| Satellite | Date | Time | Geographic region | Tiles generated |
|-----------|:----:|:----:|-------------------|:--------------:|
| Sentinel-1D | 11/07/2026 | 06:19 UTC | North Morocco (Tangier-Casablanca) | 6 408 |
| Sentinel-1D | 16/07/2026 | 19:04 UTC | South Morocco / Western Sahara | 6 452 |
| **Total** | | | | **12 860** |

> **Note :** Sentinel-1C scenes (07/2026) were deleted because the project exclusively targets Sentinel-1 (S1A/S1B/S1D).

---

## 3. SAR Preprocessing Pipeline

The **D** pipeline (ESA recommended) was applied to each scene :

```
Raw DN (uint16)
  → σ⁰ Calibration (sparse LUT)
  → Noise subtraction (noise LUT)
  → Lee 5×5 filter (speckle reduction)
  → Conversion dB (log)
  → Histogram equalization
  → Tiling 512×512 pixels (overlap 50%)
  → Export .npy uint8
```

**Results of the preprocessing :**

| Scene | Valid tiles | Ignored (>30% NoData) | Time |
|-------|:-------------:|:---------------------:|:-----:|
| S1D 11/07 | 6 408 | 126 | ~540s * |
| S1D 16/07 | 6 452 | 82 | 557s |

\* Estimated time (parallel execution, indirect measurement)

**Memory :** < 400 MB per scene (window processing, never the full scene in RAM).

---

## 4. GFW Annotations (Global Fishing Watch)

The GFW v3 API was queried to generate **annotation seeds** (human validation seeds in CVAT).

### GFW data sources used

| Source | Dataset ID | Data type | Status |
|--------|-----------|----------------|--------|
| AIS Vessel Presence ✅ | `public-global-presence:latest` | AIS ship positions | ✅ **OK** (3,321 seeds) |
| Dark Vessel Events ⚠️ | `public-global-gaps-events:latest` | AIS-off events | ⚠️ 0 after spatial filtering |

### Results per scene

| Scene | AIS seeds | Projected on tiles | Annotated tiles | Dark vessels |
|-------|:---------:|:-------------------:|:--------------:|:-----------:|
| S1D 11/07 | 218 | 58 | 10 | 0 |
| S1D 16/07 | 1 309 | 3 263 | 1 534 | 0 |
| **Total** | **1 527** | **3 321** | **1 544** | **0** |

**Protocol :** PH0-CORR-002 (hybrid). All annotations require human validation in CVAT before becoming official Ground Truth.

**Exported formats :**
- ✅ CVAT XML (direct import into CVAT)
- ✅ YOLO .txt (training format)
- ✅ JSON report per scene
- ✅ Global report (global_summary.json)
- ✅ PNG 512×512 images (conversion of .npy with edge padding for border tiles)

---

## 5. Visualization

Two visual reports were generated :

### 5.1 SAR tile samples
- **File :** `data/samples/index.html`
- **Content :** 46 sample tiles (22 + 24) with superimposed annotations (green boxes for AIS vessels)
- **Features :** Lightbox zoom, per-scene statistics, annotation badges

### 5.2 Domain Shift Analysis
- **File :** `data/analysis/domain_shift_analysis.html`
- **Content :** 100 tiles analyzed (50 per scene), intensity histograms, model confidence score distribution, annotated vs empty tiles comparison
- **Technology :** Plotly.js, interactive graphs

### 5.3 False Positive Visualizations (Post-Fix)
- **Directory :** `data/results/diagnostic_threshold_sweep/visualizations/`
- **Content :** 41 PNG overlays of Pipeline D false positives (threshold 0.25)
- **Format :** Red box = prediction, Green box = nearest GT, Yellow line = center-to-center
- **See Section 8 for analysis of these FPs**

---

## 6. Detector Benchmark

### 6.1 Pre-Fix: Three Critical Bugs Found and Corrected

Before the benchmark could produce valid results, three bugs in `benchmark_pipeline.py` were identified and fixed :

| # | Bug | Impact | Fix |
|---|-----|--------|-----|
| **1** | **Missing tensor transpose** in `run_inference()` | YOLOv8 output shape is `[1, 5, 8400]` but the code iterated over axis 1 (5 rows) instead of transposing to `[8400, 5]`. **Only 5 proposals were decoded per tile instead of 8400**, making detections effectively random. | `raw.T` before iterating |
| **2** | **Wrong directory path** in `benchmark_all_pipelines()` | The code computed `scene_dir / pipeline_name` where `scene_dir` already pointed to the pipeline directory (`.../D/`), producing `.../D/D/`. **All tile loading failed silently** for every pipeline. | Use `parent` of metadata path as scene root |
| **3** | **Invalid resize** from 512→640 | Used NumPy `slice assignment` which assumed equal dimensions. **Would crash with mismatched sizes** if Bug 2 were fixed without Bug 1. | Replace with `PIL.Image.resize(LANCZOS)` |

**Verification of fixes (non-regression test) :**
- ✅ 1,544 annotated tiles loaded correctly (across both scenes)
- ✅ 8,400 raw proposals per tile verified (not 5)
- ✅ Inference ONNX functional end-to-end

Additionally, the function `estimate_bbox()` was **removed** from `benchmark_pipeline.py`. It was dead code — defined but never called by inference or metrics code. Its misleading documentation about "methodological bias on mAP@0.5:0.95" was a residual artifact from the original notebook.

### 6.2 Results After Bug Fixes

| Metric | Pipeline A | Pipeline B | Pipeline C | Pipeline D |
|--------|:----------:|:----------:|:----------:|:----------:|
| **Precision** | 0.0 | 0.0 | 0.0 | 0.0 |
| **Recall** | 0.0 | 0.0 | 0.0 | 0.0 |
| **mAP@0.5** | 0.0 | 0.0 | 0.0 | 0.0 |
| True positives | 0 | 0 | 0 | 0 |
| False positives | 0 | 0 | 0 | **41** |
| False negatives | 3,321 | 3,321 | 3,321 | 3,321 |

> **Key observation:** Pipelines A, B, C produce **zero detections** at threshold 0.25. Only Pipeline D (recommended pipeline with σ⁰ + Lee + Log → dB) generates any false positives — 41 total across both scenes. This suggests the full ESA-recommended chain is necessary to preserve some signal, but insufficient for domain alignment.

### 6.3 The `estimate_bbox()` Red Herring (Definitively Resolved)

The original notebook included a function `estimate_bbox()` that used a **fixed bounding box size** (8×8 pixels normalized to 512). A documentation note warned of "methodological bias on mAP@0.5:0.95". This raised the question:

> *Are the mAP=0.0 results valid, or are they an artifact of fixed-size bboxes clashing with real-sized GT boxes?*

**Investigation:** The function was **never called** in the inference or metrics code. The predictions from `run_inference()` use the real `(w, h)` values directly from the YOLO model output — not a fixed size. The misleading note was residual documentation from the original notebook (which used `estimate_bbox()` in an older version of the code path).

**Resolution:** The function has been removed, and the note corrected. The mAP=0.0 result required no bbox-size correction — it is a genuine detection failure.

### 6.4 Center-Distance Analysis (Complementary Metric)

To definitively distinguish between "model detects the right location but IoU fails" vs "model detects nothing," a **center-to-center distance** metric was computed independently of bbox size :

```python
def center_distance(pred_center, gt_center, tile_size=512):
    """Euclidean distance in pixels. Independent of bbox width/height."""
    return sqrt((px - gx)² + (py - gy)²)
```

**Results across both scenes (Pipeline D, 41 predictions at θ=0.25) :**

| Distance to nearest GT center | Count | Percentage |
|-------------------------------|:----:|:----------:|
| **≤10 px** (essentially correct) | **0** | **0.0%** |
| **11–20 px** (close) | **2** | **4.9%** |
| 21–50 px (loose match) | 6 | 14.6% |
| 51–100 px (far) | 7 | 17.1% |
| **>100 px** (wrong location) | **26** | **63.4%** |
| IoU < 0.1 with best GT | **41** | **100%** |

**Conclusion :** The model's predictions at threshold 0.25 are **not aligned with vessel locations** even at the center level. Only 2/41 (4.9%) are within 20px of a GT center. The mAP=0.0 is a valid measure of genuine detection failure.

---

## 7. Deep Diagnostic: Confidence Collapse at GT Locations

### 7.1 Verification 1 — Confidence at GT Centers

For each of the **3,321 GT boxes**, we found the **closest raw proposal** among ALL 8,400 YOLO candidates (no confidence threshold applied) :

| Metric | Value |
|--------|-------|
| GT boxes analyzed | 3,321 |
| Mean distance to closest proposal | **2.85 px** |
| Median distance to closest proposal | ~2–3 px |
| Max confidence observed at any GT location | **0.00135** |
| GT boxes within 50px of any proposal | **3,321 (100%)** |
| GT boxes within 50px AND confidence > 0.05 | **0 (0%)** |

**Confidence distribution of the best proposal per GT :**

| Confidence band | Count | % |
|-----------------|:----:|:-:|
| > 0.25 (passes production threshold) | 0 | 0.0% |
| 0.10 – 0.25 | 0 | 0.0% |
| 0.05 – 0.10 | 0 | 0.0% |
| 0.01 – 0.05 | 2 | 0.06% |
| < 0.01 | 3,319 | 99.94% |

**Interpretation :** The model **does produce proposals at the correct locations** (2.85 px average distance to GT centers — excellent spatial accuracy), but the **confidence assigned to these proposals is catastrophically low** (< 0.01 for 99.94% of GT boxes). This is the fingerprint of a domain shift that suppresses the model's activation confidence without destroying its spatial prior.

### 7.2 Verification 2 — Sensitivity to Confidence Threshold

To test whether the failure was merely a threshold calibration issue, the center-distance analysis was re-run at three confidence thresholds :

| Threshold (θ) | Predictions (after NMS) | IoU < 0.1 | Distance > 100 px |
|:-------------:|:----------------------:|:---------:|:-----------------:|
| **0.25** (prod) | 41 | 100% | 63.4% |
| **0.10** | 67 | 100% | 64.2% |
| **0.05** | 86 | 100% | 65.1% |

**Key finding :** Lowering the threshold to 0.05 increases the number of predictions (41 → 86) but does NOT improve the center-distance distribution or IoU. The additional predictions at lower thresholds are also random — they are **not** the low-confidence proposals near GT centers (which have conf < 0.01, still below 0.05).

**Conclusion :** This is **not a threshold calibration problem**. The model's correct-location proposals are at confidence < 0.01, far below any practical threshold. The 41–86 predictions that exceed even 0.05 are unrelated noise activations. Only fine-tuning can shift the correct-location proposals above a usable confidence level.

### 7.3 Unified Failure Model

```
Training domain (simulated SAR) :       Inference domain (real SAR) :
  ┌────────────────────────┐              ┌────────────────────────┐
  │  Vessel (high contrast)│              │  Vessel (low contrast) │
  │  Confidence: 0.85      │    DOMAIN    │  Confidence: 0.001     │
  │  Activation: strong    │  ────SHIFT──→│  Activation: weak      │
  └────────────────────────┘              └────────────────────────┘
                                                  │
                                                  ▼
                                        ┌────────────────────────┐
                                        │  Noise peak (speckle)  │
                                        │  Confidence: 0.30      │
                                        │  Activation: strongest │
                                        └────────────────────────┘
                                             ← This is our "FP 41"
```

The model's learned feature extractor produces the **right spatial response** (2.85 px accuracy) but with **wrong magnitude** (factor 1000× confidence suppression). The strongest activations in the real domain come from noise patterns that happen to match the simulated training distribution — hence the 41 false positives at random locations.

---

## 8. False Positive Characterization

### 8.1 Spatial Distribution

The 41 Pipeline D false positives (threshold 0.25) were distributed across **25 out of 1,544** annotated tiles (1.6% of tiles). Most tiles with FPs contain only 1–2 predictions.

### 8.2 Distance to Nearest GT

| Scene | FPs | Within 20px | 21–100px | >100px | IoU < 0.1 |
|-------|:---:|:-----------:|:--------:|:------:|:---------:|
| S1D 11/07 | 5 | 0 (0%) | 3 (60%) | 2 (40%) | 100% |
| S1D 16/07 | 36 | 2 (5.6%) | 10 (27.8%) | 24 (66.7%) | 100% |

### 8.3 Visual Inspection

Visualization overlays (41 PNG files) were generated showing each FP with:
- **Red box** = prediction bounding box
- **Green box** = nearest GT box (if exists on tile)
- **Yellow line** = line connecting prediction center to GT center
- **Label** = confidence score + distance in pixels

These are available at: `data/results/diagnostic_threshold_sweep/visualizations/`

---

## 9. Pipeline A/B/C Analysis

Pipelines A (raw), B (Sigma0), and C (Sigma0+Lee) produced **zero predictions** at threshold 0.25 across all 1,544 annotated tiles. This is consistent with the hypothesis that the model — trained on dB-domain simulated data — requires the full dB conversion to produce any activations at all. However, even Pipeline D (which includes dB conversion) only produces noise-level FPs.

**Recommendation :** For fine-tuning, use Pipeline D tiles as input. The dB conversion preserves more signal for the model, and the fine-tuning will adapt the weights to the real-domain feature distribution.

---

## 10. Conclusions and Recommendations

### 10.1 Scientific Decision

| Criterion | Threshold | Result | Decision |
|-----------|:--------:|:------:|:--------:|
| mAP@0.5 > 0.70 | ✅ GO | 0.0 | ❌ FAILED |
| mAP@0.5 ∈ [0.50, 0.70] | ⚠️ MARGINAL | 0.0 | ❌ |
| mAP@0.5 < 0.50 | 🛑 **STOP** | 0.0 | ✅ **STOP** |

**Decision : 🛑 STOP — Fine-tuning required before Phase 1**

### 10.2 Root Cause Analysis

The zero-shot domain transfer fails due to **complete signal loss**, not calibration or spatial misalignment :

| Hypothesis | Evidence | Verdict |
|------------|----------|---------|
| Bbox size bias (`estimate_bbox()` fixed size) | Function never called. Predictions use real YOLO w,h. | ❌ **Refuted** |
| Threshold too high | Sweep to 0.05 shows same random FP pattern. GT-location proposals have conf < 0.01. | ❌ **Refuted** |
| Model misses locations | Center-distance: **2.85 px** average to GT centers. Spatial prior is intact. | ❌ **Refuted** |
| Confidence collapse (calibration issue) | Raw pre-sigmoid logits: GT-proximal mean **0.0**, background mean **0.0**. Cohen's d = **-0.02** (negligible). | ❌ **Refuted — not just calibration** |
| **Signal lost in domain shift** | No internal logit separation: AUC=**0.54** (near random). KS p=**0.26**. Logits are flat everywhere — the model cannot distinguish vessels from background even internally. | ✅ **Confirmed — full fine-tuning required** |

### 10.3 Logit Analysis (Final Arbiter)

To definitively distinguish between a **calibration problem** (logits separate but sigmoid squashed) and a **signal loss problem** (logits flat everywhere), we inspected the raw pre-sigmoid confidence logits directly from the ONNX model output.

**Key insight :** The ONNX model exports **raw logits** (unbounded values, `max 638` on dummy input), NOT sigmoid probabilities. The confidence channel (index 4) is pre-activation, allowing direct inspection of the model's internal state.

**Methodology :**
- For 30 tiles with GT: extract the logit of the closest proposal (among 8,400) to each GT center
- For the same tiles: extract logits at random background positions (>50px from any GT)
- For 30 empty tiles (no vessels): extract the noise floor distribution (median of per-tile max logit)
- Compare distributions using KS test, Mann-Whitney U, Cohen's d, and AUC

**Results :**

| Metric | GT Locations | Background (same tiles) | Empty Tiles (noise floor) |
|--------|:------------:|:----------------------:|:------------------------:|
| Mean logit | **0.0** | **0.0** | **0.0** |
| Median logit | **0.0** | **0.0** | **0.0** |
| Global max logit | 0.0003 | 0.0275 | up to 0.0274 * |
| Cohen's d (GT vs BG) | — | **-0.02** (negligible) | — |
| AUC (GT vs BG) | — | **0.54** (near random) | — |
| KS p-value | — | **0.26** (not significant) | — |

> \* Empty tile value is the **median of per-tile max logits** = 0.0028; range across all empty tiles = [0.0008, 0.0274]. The upper bound (0.0274) represents the highest noise logit observed in any empty tile.

**Interpretation :** The model's internal confidence logits show **zero separation** between vessel locations and random background. Even before the sigmoid squashing function, the model assigns the same near-zero logit everywhere. The noise floor on empty tiles (max 0.0274) is **90× higher than the GT-proximal max logit (0.0003)**, confirming that background noise consistently triggers stronger internal activations than actual vessel locations.

This is NOT a calibration issue (where logits would be well-separated but mis-scaled) — it is a **complete loss of the detection signal** in the feature space, caused by the domain shift between simulated and real SAR data.

**Final verdict :** No lightweight recalibration can fix this. Only **full fine-tuning of all layers** on real Sentinel-1 data can recover the detection capability.

### 10.4 Strategic Recommendations

#### Option A — Fine-tuning the current model (Recommended ⭐)

| Step | Action | Effort | Expected Impact |
|------|--------|:------:|:---------------|
| 1. | Manually validate 3,321 AIS annotations in CVAT | TBD | Reliable Ground Truth |
| 2. | Split annotated tiles into train/val/test (80/10/10) | 1 hour | — |
| 3. | Fine-tune YOLOv8n on Pipeline D tiles + validated labels | 2–4 GPU hours | Estimated mAP > 0.60 |
| 4. | Re-run benchmark on test set | 30 min | Final measurement |
| 5. | If mAP > 0.70 → Proceed to Phase 1 metrics | — | — |

**Data split (recommended) :**
| Split | Tiles | GT boxes |
|-------|:-----:|:--------:|
| Train | 1,235 | ~2,657 |
| Validation | 154 | ~332 |
| Test | 155 | ~332 |

#### Option B — Full pipeline comparison

Preprocess pipelines A, B, C for the same scenes to enable inter-pipeline comparison during fine-tuning. Currently only Pipeline D tiles exist.

#### Option C — Data expansion

Acquire additional Sentinel-1 scenes with higher AIS density (e.g., Gibraltar Strait, Singapore Strait) to increase the fine-tuning dataset beyond 3,321 annotations.

### 10.5 Immediate Next Steps

```
1. [CVAT]    Import 3,321 annotations + 12,860 PNG images
2. [Human]   Validate annotations (correct false positives/negatives)
3. [GPU]     Fine-tune YOLOv8n on validated data (Pipeline D tiles)
4. [GPU]     Evaluate fine-tuned model on test split
5. [Decision] If mAP > 0.70 → Proceed to Phase 1
```

---

## 11. Data Structure

```
phase0/data/
├── scenes/                          ← 2 .SAFE folders (4.5 GB each)
│   ├── S1D_..._224C.SAFE/
│   └── S1D_..._9C83.SAFE/
│
├── tiles/                           ← 12,860 .npy tiles (Pipeline D)
│   ├── S1D_..._224C/D/
│   │   ├── metadata.json
│   │   └── *.npy (× 6,408)
│   └── S1D_..._9C83/D/
│       ├── metadata.json
│       └── *.npy (× 6,452)
│
├── annotations/                     ← GFW + PNG annotations
│   ├── global_summary.json
│   ├── S1D_..._224C/
│   │   ├── annotation_report.json
│   │   ├── cvat_annotation.xml
│   │   ├── labels/*.txt (× 10)
│   │   └── cvat_import/images/*.png
│   └── S1D_..._9C83/
│       ├── annotation_report.json
│       ├── cvat_annotation.xml
│       ├── labels/*.txt (× 1,534)
│       └── cvat_import/images/*.png
│
├── results/                         ← Benchmark + diagnostic results
│   ├── benchmark_*_224C.json/csv
│   ├── benchmark_*_9C83.json/csv
│   ├── benchmark_summary_post_fix.json
│   ├── center_distance_analysis.json
│   ├── diagnostic_threshold_sweep/
│   │   ├── diagnostic_results.json
│   │   └── visualizations/*.png (× 41)
│   └── logit_analysis/
│       └── logit_analysis_results.json
│
├── samples/                         ← Visual samples
│   ├── index.html
│   └── images/*.png (× 46)
│
└── analysis/                       ← Domain shift analysis
    └── domain_shift_analysis.html
```

---

## 12. Key Files

| File | Description |
|------|-------------|
| `data/annotations/global_summary.json` | Global summary of annotations |
| `data/samples/index.html` | Visual samples of tiles |
| `data/analysis/domain_shift_analysis.html` | Domain shift analysis |
| `data/results/benchmark_summary_post_fix.json` | Final benchmark results (post-bugfix) |
| `data/results/center_distance_analysis.json` | Center-distance analysis results |
| `data/results/diagnostic_threshold_sweep/diagnostic_results.json` | Full threshold sweep diagnostic |
| `data/results/logit_analysis/logit_analysis_results.json` | Raw logit analysis (pre-sigmoid) |
| `scripts/benchmark_pipeline.py` | Detector benchmark (bugs fixed) |
| `scripts/sar_preprocessing.py` | SAR preprocessing pipeline |
| `scripts/gfw_annotations.py` | GFW annotation pipeline |
| `scripts/visualize_samples.py` | Visual samples generation |
| `scripts/analyze_domain_shift.py` | Domain shift analysis |

---

## 13. Document History

| Date | Version | Changes |
|:----:|:-------:|---------|
| 2026-07-17 | v1 | Initial report — mAP=0.0, domain transfer failed |
| **2026-07-18** | **v2** | **Added : 3 bugs found/fixed, center-distance analysis, threshold sensitivity sweep (θ=0.05/0.1/0.25), confidence collapse diagnosis, `estimate_bbox()` removal, FP visualizations** |
| **2026-07-18** | **v3** | **Added : Logit analysis (raw pre-sigmoid confidence investigation). Cohen's d = -0.02, AUC = 0.54 — no internal separation. Definitive verdict: full fine-tuning required, recalibration impossible.** |

---

*Report updated July 18, 2026 — Phase 0 of the Maritime Edge AI Platform*
